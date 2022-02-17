from toolz import get_in
import xarray as xr
import numpy as np
from functools import partial
from datacube.utils import masking
from odc.algo import keep_good_only, erase_bad, enum_to_bool
from odc.algo._masking import _xr_fuse, _first_valid_np, mask_cleanup, _fuse_or_np
from odc.algo.io import load_with_native_transform
from datacube.model import Dataset
from datacube.utils.geometry import GeoBox
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple
from odc.stats.plugins import StatsPluginInterface
from odc.stats.plugins._registry import register


class NDVIAnomaly(StatsPluginInterface):
    NAME = "NDVIAnomaly"
    SHORT_NAME = NAME
    VERSION = "1.0.0"
    PRODUCT_FAMILY = "statistics"

    def __init__(
        self,
        resampling: str = "bilinear",
        bands_ls89: Optional[Sequence[str]] = ["red", "nir", "green", "blue"],
        bands_s2: Optional[Sequence[str]] = ["red", "nir_2"],
        mask_band_ls89: str = "QA_PIXEL",
        mask_band_s2: str = "SCL",
        group_by: str = "solar_day",
        flags_s2: Optional[Sequence[str]] = [
            "cloud high probability",
            "cloud medium probability",
            "thin cirrus",
            "cloud shadows",
            "saturated or defective",
        ],
        flags_ls89: Dict[str, Optional[Any]] = dict(
            cloud="high_confidence",
            cloud_shadow="high_confidence",
            cirrus="high_confidence",
        ),
        nodata_flags_ls89: Dict[str, Optional[Any]] = dict(nodata=False),
        nodata_flags_s2: Optional[Sequence[str]] = ['no data'],
        filters: Optional[Iterable[Tuple[str, int]]] = None,
        rolling_window: int = 3,
        work_chunks: Dict[str, Optional[Any]] = dict(x=1600, y=1600),
        scale: float = 0.0000275,
        offset: float = -0.2,
        output_dtype: str = "float32",
        output_bands: Tuple[str, ...] = ("mean_ndvi", "ndvi_std_anomaly", "clear_count"),
        **kwargs,
    ):

        self.bands_ls89 = bands_ls89
        self.bands_s2 = bands_s2
        self.output_bands = output_bands
        self.mask_band_ls89 = mask_band_ls89
        self.mask_band_s2 = mask_band_s2
        self.rolling_window = rolling_window
        self.group_by = group_by
        self.input_bands_ls89 = tuple(bands_ls89) + (mask_band_ls89,)
        self.input_bands_s2 = tuple(bands_s2) + (mask_band_s2,)
        self.flags_ls89 = flags_ls89
        self.flags_s2 = flags_s2
        self.resampling = resampling
        self.nodata_flags_ls89 = nodata_flags_ls89
        self.nodata_flags_s2 = nodata_flags_s2
        self.filters = filters
        self.work_chunks = work_chunks
        self.scale = scale
        self.offset = offset
        self.output_dtype = np.dtype(output_dtype)
        self.output_nodata = np.nan

    @property
    def measurements(self) -> Tuple[str, ...]:
        return self.output_bands

    def input_data(self, datasets: Sequence[Dataset], geobox: GeoBox) -> xr.Dataset:
        """
        Load 
        """

        def masking_data_ls(xx, flags):

            # remove negative pixels, pixels > than the maxiumum valid range for LS (65,455),
            # and pixels where the blue band is above 20,000 (removes cloud missed by fmask)
            valid = (
                (
                    (xx[self.bands_ls89] > (-1.0 * self.offset / self.scale))
                    & (xx[self.bands_ls89] < 65455)
                )
                .to_array(dim="band")
                .all(dim="band")
            )

            # remove cloud that fmask misses
            missed_cloud = xx["blue"] >= 20910  # i.e. > 0.375
            missed_cloud = mask_cleanup(missed_cloud, mask_filters=[("dilation", 5)])

            mask_band = xx[self.mask_band_ls89]
            xx = xx.drop_vars([self.mask_band_ls89])

            flags_def = masking.get_flags_def(mask_band)

            # set cloud_mask - True=cloud, False=non-cloud
            mask, _ = masking.create_mask_value(flags_def, **flags)
            cloud_mask = (mask_band & mask) != 0
            cloud_mask = xr.ufuncs.logical_or(
                cloud_mask, missed_cloud
            )  # combine with 'missed_cloud'

            # set no_data bitmask - True=data, False=no-data
            nodata_mask, _ = masking.create_mask_value(flags_def, **self.nodata_flags_ls89)
            keeps = (mask_band & nodata_mask) == 0
            xx = keep_good_only(xx, valid)  # remove negative and oversaturated pixels
            xx = keep_good_only(xx, keeps)  # remove nodata pixels

            # add the pq layers to the dataset
            xx["cloud_mask"] = cloud_mask

            # remove green and blue bands
            # (only have these bands to ID more bad pixels e.g. 'tractor tread')
            xx = xx.drop_vars(["green", "blue"])

            return xx
        
        def masking_data_s2(xx, flags):

            mask_band = xx[self.mask_band_s2]
            xx = xx.drop_vars([self.mask_band_s2])
            pq_mask = enum_to_bool(mask=mask_band, categories=self.flags_s2)
            
            # Erase nodata pixels
            keeps = enum_to_bool(mask=mask_band, categories=self.nodata_flags_s2, invert=True)
            xx = keep_good_only(xx, keeps) 

            # add the pq layers to the dataset
            xx["cloud_mask"] = pq_mask

            return xx

        # seperate datsets into different sensors
        product_dss = {}
        for dataset in datasets:
            product = get_in(["product", "name"], dataset.metadata_doc)
            if product not in product_dss:
                product_dss[product] = []
            product_dss[product].append(dataset)
        
        #print(product_dss['ndvi_climatology_ls'])
        
        # Separate out LS89 datasets from s2
        ls_dss = []
        if "ls8_sr" in product_dss:
            ls_dss = ls_dss + product_dss["ls8_sr"]

        if "ls9_sr" in product_dss:
            ls_dss = ls_dss + product_dss["ls9_sr"]
    
        # load landsat 8/9.
        ls89 = load_with_native_transform(
            dss=ls_dss,
            geobox=geobox,
            native_transform=lambda x: masking_data_ls(x, self.flags_ls89),
            bands=self.input_bands_ls89,
            groupby=self.group_by,
            fuser=self.fuser,
            chunks=self.work_chunks,
            resampling=self.resampling,
        )

        # load s2
        s2 = load_with_native_transform(
            dss=product_dss["s2_l2a"],
            geobox=geobox,
            native_transform=lambda x: masking_data_s2(x, self.flags_s2),
            bands=self.input_bands_s2,
            groupby=self.group_by,
            fuser=self.fuser,
            chunks=self.work_chunks,
            resampling=self.resampling,
        )

        # add datasets to dict
        ds = dict(ls89=ls89, s2=s2)
    
        # Loop through datasets, rescale to SR, calculate NDVI
        for k in ds:

            # seperate pq layers
            cloud_mask = ds[k]["cloud_mask"]

            # morphological operators on cloud dataset to improve it
            if self.filters is not None:
                cloud_mask = mask_cleanup(cloud_mask, mask_filters=self.filters)

            # erase pixels with dilated cloud
            ds[k] = ds[k].drop_vars(["cloud_mask"]) 
            ds[k] = erase_bad(ds[k], cloud_mask)

            # rescale bands into surface reflectance scale if dataset is Landsat 8/9
            if k == 'ls89':
                for band in ds[k].data_vars.keys():
                    # set nodata_mask - use for resetting nodata pixel after rescale
                    nodata_mask = ds[k][band] == ds[k][band].attrs.get("nodata")
                    # rescale
                    ds[k][band] = self.scale * ds[k][band] + self.offset
                    #  apply nodata_mask - reset nodata pixels to output-nodata
                    ds[k][band] = ds[k][band].where(~nodata_mask, self.output_nodata)
                    # set data-type and nodata attrs
                    ds[k][band] = ds[k][band].astype(self.output_dtype)
                    ds[k][band].attrs["nodata"] = self.output_nodata
            
            if k == 's2':
                ds[k] = ds[k].rename({'nir_2':'nir'})
            
            # calculate ndvi
            ds[k]["ndvi"] = (ds[k].nir - ds[k].red) / (ds[k].nir + ds[k].red)

            # remove remaining SR bands
            ds[k] = ds[k].drop_vars(["red", "nir"])

        # combine data arrays
        ndvi = xr.concat([ds["ls89"],ds["ls89"]], dim='spec').sortby('spec')

        # Remove NDVI's that aren't between 0 and 1
        ndvi = ndvi.where((ndvi >= 0) & (ndvi <= 1))

        return ndvi

    def reduce(self, xx: xr.Dataset) -> xr.Dataset:
        """
        Collapse the NDVI time series using mean
        """
        # create boolean of valid obs (not NaNs)
        cc = xr.ufuncs.isnan(xx.ndvi)
        cc = xr.ufuncs.logical_not(cc)  # invert
        cc = cc.to_dataset(name="clear_count")
        xx_pq = cc.sum("spec")

        # smooth timeseries with rolling mean
        # doing this AFTER clear count as rolling mean changes # of obs.
        xx["ndvi"] = xx.ndvi.rolling(spec=self.rolling_window, min_periods=1).mean()

        # remask so rolling mean doesn't change # of obs
        xx["ndvi"] = xx["ndvi"].where(cc["clear_count"])
        print(xx)
        print(xx.time.values)
        # mapping month names with month int
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        
        #find the month we've loaded from time dim
        m = xx.spec['time'].dt.month.values[0]
        
        #get month we're loading as abbreviated str
        month = list(months.keys())[list(months.values()).index(m)]
        print(month)
        ndvi_clim = load_with_native_transform(
            dss=product_dss["ndvi_climatology_ls"],
            geobox=geobox,
            bands=['mean_'+month, 'stddev_'+month, 'count_'+month],
            chunks=self.work_chunks,
            resampling=self.resampling,
        )
        
        # calculate the mean for the month
        xx_mean = xx.mean("spec")
        
        #calculate anomaly
        anomalies = xr.apply_ufunc(
            lambda x, m, s: (x - m) / s,
            xx_mean,
            ndvi_clim['mean_'+month],
            ndvi_clim['stddev_'+month],
            output_dtypes=[xx.dtype],
            dask="allowed"
        )
        
        #rename arrays
        anomalies = anomalies.to_array(name="ndvi_std_anomaly").drop("variable").squeeze()
        anomalies = anomalies.astype(np.float32)
        xx_mean = xx_mean.to_array(name="mean_ndvi").drop("variable").squeeze()
        xx_mean = xx_mean.astype(np.float32)
        xx_pq = xx_pq.to_array(name="clear_count").drop("variable").squeeze()
        xx_pq = xx_pq.astype(np.int16)
                                       
        # merge them all into one dataset
        anom = xr.merge([anomalies, xx_mean, xx_pq], compat="override")

        return anom

    def fuser(self, xx):
        """
        Fuse cloud_mask with OR
        """
        cloud_mask = xx["cloud_mask"]
        xx = _xr_fuse(
            xx.drop_vars(["cloud_mask"]), partial(_first_valid_np, nodata=0), ""
        )
        xx["cloud_mask"] = _xr_fuse(cloud_mask, _fuse_or_np, cloud_mask.name)

        return xx


register("ndvi_tools.ndvi_anomaly_plugin", NDVIAnomaly)