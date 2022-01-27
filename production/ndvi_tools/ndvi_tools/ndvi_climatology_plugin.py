from toolz import get_in
import xarray as xr
import numpy as np
from functools import partial
from datacube.utils import masking
from odc.algo import keep_good_only, erase_bad
from odc.algo._masking import _xr_fuse, _first_valid_np, mask_cleanup, _fuse_or_np
from odc.algo.io import load_with_native_transform
from datacube.model import Dataset
from datacube.utils.geometry import GeoBox
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple
from odc.stats.plugins import StatsPluginInterface
from odc.stats.plugins._registry import register


class NDVIClimatology(StatsPluginInterface):
    NAME = "NDVIClimatology"
    SHORT_NAME = NAME
    VERSION = "1.0.0"
    PRODUCT_FAMILY = "statistics"

    def __init__(
        self,
        resampling: str = "bilinear",
        bands: Optional[Sequence[str]] = ["red", "nir", "green", "blue"],
        mask_band: str = "QA_PIXEL",
        harmonization_slope: float = None,
        harmonization_intercept: float = None,
        rolling_window: int = 3,
        group_by: str = "solar_day",
        flags_ls57: Dict[str, Optional[Any]] = dict(
            cloud="high_confidence", cloud_shadow="high_confidence"
        ),
        flags_ls8: Dict[str, Optional[Any]] = dict(
            cloud="high_confidence",
            cloud_shadow="high_confidence",
            cirrus="high_confidence",
        ),
        nodata_flags: Dict[str, Optional[Any]] = dict(nodata=False),
        filters: Optional[Iterable[Tuple[str, int]]] = None,
        work_chunks: Dict[str, Optional[Any]] = dict(x=1600, y=1600),
        scale: float = 0.0000275,
        offset: float = -0.2,
        output_dtype: str = "float32",
        output_bands: Tuple[str, ...] = (
            "mean_jan",
            "mean_feb",
            "mean_mar",
            "mean_apr",
            "mean_may",
            "mean_jun",
            "mean_jul",
            "mean_aug",
            "mean_sep",
            "mean_oct",
            "mean_nov",
            "mean_dec",
            "stddev_jan",
            "stddev_feb",
            "stddev_mar",
            "stddev_apr",
            "stddev_may",
            "stddev_jun",
            "stddev_jul",
            "stddev_aug",
            "stddev_sep",
            "stddev_oct",
            "stddev_nov",
            "stddev_dec",
            "count_jan",
            "count_feb",
            "count_mar",
            "count_apr",
            "count_may",
            "count_jun",
            "count_jul",
            "count_aug",
            "count_sep",
            "count_oct",
            "count_nov",
            "count_dec",
        ),
        **kwargs,
    ):

        self.bands = bands
        self.output_bands = output_bands
        self.mask_band = mask_band
        self.harmonization_slope = harmonization_slope
        self.harmonization_intercept = harmonization_intercept
        self.rolling_window = rolling_window
        self.group_by = group_by
        self.input_bands = tuple(bands) + (mask_band,)
        self.flags_ls57 = flags_ls57
        self.flags_ls8 = flags_ls8
        self.resampling = resampling
        self.nodata_flags = nodata_flags
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
        Load each of the sensors, remove cloud and poor data,
        apply scaling coefficients to LS5 & 7 NDVI to mimic
        NDVI of Landsat 8. Return the harmonized NDVI time series
        """

        def masking_data(xx, flags):
            """
            Loads in the data in the native projection. It performs the following:

            1. Loads pq bands
            2. Extract valid - by removing negative pixel using masking_scale from input bands
            3. Extract cloud_mask flags from bands
            4. Drop nodata and negative pixels
            5. Add cloud_mask band to xx for fuser and reduce
            """

            # remove negative pixels, pixels > than the maxiumum valid range for LS (65,455),
            # and pixels where the blue band is above 20,000 (removes cloud missed by fmask)
            valid = (
                (
                    (xx[self.bands] > (-1.0 * self.offset / self.scale))
                    & (xx[self.bands] < 65455)
                )
                .to_array(dim="band")
                .all(dim="band")
            )
            
            # remove missed cloud that fmask misses
            missed_cloud =  xx['blue'] >= 20910 # i.e. > 0.375
            missed_cloud = mask_cleanup(missed_cloud, mask_filters=[("dilation", 5)])
            
            mask_band = xx[self.mask_band]
            xx = xx.drop_vars([self.mask_band])

            flags_def = masking.get_flags_def(mask_band)

            # set cloud_mask - True=cloud, False=non-cloud
            mask, _ = masking.create_mask_value(flags_def, **flags)
            cloud_mask = (mask_band & mask) != 0
            cloud_mask = xr.ufuncs.logical_or(cloud_mask, missed_cloud) # combine with 'missed_cloud'
                
            # set no_data bitmask - True=data, False=no-data
            nodata_mask, _ = masking.create_mask_value(flags_def, **self.nodata_flags)
            keeps = (mask_band & nodata_mask) == 0
            xx = keep_good_only(xx, valid)  # remove negative and oversaturated pixels
            xx = keep_good_only(xx, keeps)  # remove nodata pixels
            
            # add the pq layers to the dataset
            xx["cloud_mask"] = cloud_mask

            # remove green and blue bands
            # (only have these bands to ID more bad pixels e.g. 'tractor tread')
            xx = xx.drop_vars(["green", "blue"])

            return xx

        # seperate datsets into different sensors
        product_dss = {}
        for dataset in datasets:
            product = get_in(["product", "name"], dataset.metadata_doc)
            if product not in product_dss:
                product_dss[product] = []
            product_dss[product].append(dataset)

        # Separate out LS5,7 datasets
        ls57_dss = []
        if "ls5_sr" in product_dss:
            ls57_dss = ls57_dss + product_dss["ls5_sr"]

        if "ls7_sr" in product_dss:
            ls57_dss = ls57_dss + product_dss["ls7_sr"]

        # load landsat 5 and/or 7. We need to wrap this in a
        # try-except because some tiles don't have ls57 data
        try:
            ls57 = load_with_native_transform(
                dss=ls57_dss,
                geobox=geobox,
                native_transform=lambda x: masking_data(x, self.flags_ls57),
                bands=self.input_bands,
                groupby=self.group_by,
                fuser=self.fuser,
                chunks=self.work_chunks,
                resampling=self.resampling,
            )
        except ValueError:
            pass

        # load Landsat 8
        ls8 = load_with_native_transform(
            dss=product_dss["ls8_sr"],
            geobox=geobox,
            native_transform=lambda x: masking_data(x, self.flags_ls8),
            bands=self.input_bands,
            groupby=self.group_by,
            fuser=self.fuser,
            chunks=self.work_chunks,
            resampling=self.resampling,
        )

        # determine if there was ls57 data
        try:
            ls57
        except NameError:
            ls57_exists = False
        else:
            ls57_exists = True

        # add datasets to dict
        if ls57_exists:
            ds = dict(ls57=ls57, ls8=ls8)
        else:
            ds = dict(ls8=ls8)

        # Loop through datasets, rescale to SR, calculate NDVI
        for k in ds:

            # seperate pq layers
            cloud_mask = ds[k]["cloud_mask"]

            # morphological operators on cloud dataset to improve it
            if self.filters is not None:
                cloud_mask = mask_cleanup(cloud_mask, mask_filters=self.filters)

            # erase pixels with dilated cloud
            ds[k] = ds[k].drop_vars(["cloud_mask"])  # "keeps"
            ds[k] = erase_bad(ds[k], cloud_mask)

            # rescale bands into surface reflectance scale
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

            # calculate ndvi
            ds[k]["ndvi"] = (ds[k].nir - ds[k].red) / (ds[k].nir + ds[k].red)

            # remove remaining SR bands
            ds[k] = ds[k].drop_vars(["red", "nir"])

        if ls57_exists:
            # harmonization of LS57 NDVI to match LS8 NDVI
            ds["ls57"]["ndvi"] = (
                ds["ls57"]["ndvi"] - self.harmonization_intercept
            ) / self.harmonization_slope

            # combine harmonized datarrays
            ndvi = ds["ls57"].combine_first(ds["ls8"])

        else:
            ndvi = ds["ls8"]

        # Remove NDVI's that aren't between 0 and 1
        ndvi = ndvi.where((ndvi >= 0) & (ndvi <= 1))

        return ndvi

    def reduce(self, xx: xr.Dataset) -> xr.Dataset:
        """
        Collapse the NDVI time series using mean
        and std. dev.
        """
        # create boolean of valid obs (not NaNs)
        cc = xr.ufuncs.isnan(xx.ndvi)
        cc = xr.ufuncs.logical_not(cc) # invert
        cc = cc.to_dataset(name="clear_count")
        xx_pq = cc.groupby(cc.spec["time.month"]).sum("spec") # clear count per month

        # smooth timeseries with rolling mean
        # doing this AFTER clear count as rolling mean changes # of obs.
        xx["ndvi"] = xx.ndvi.rolling(
            spec=self.rolling_window, min_periods=1).median()
        
        # remask so rolling mean doesn't change # of obs
        xx["ndvi"] = xx["ndvi"].where(cc['clear_count'])
        
        # Climatology calulations
        months = {
            "jan": [1],
            "feb": [2],
            "mar": [3],
            "apr": [4],
            "may": [5],
            "jun": [6],
            "jul": [7],
            "aug": [8],
            "sep": [9],
            "oct": [10],
            "nov": [11],
            "dec": [12],
        }

        # calculate the climatologies for each month
        xx_mean = xx.groupby(xx.spec["time.month"]).mean("spec")
        xx_std = xx.groupby(xx.spec["time.month"]).std("spec")

        # loop through months, select out arrays, rename
        ndvi_var_mean = []
        ndvi_var_std = []
        pq = []
        for m in months:
            # mean
            ix_mean = xx_mean.sel(month=months[m])
            ix_mean = ix_mean.to_array(name="mean_" + m).drop("variable").squeeze()
            ix_mean = ix_mean.astype(np.float32)

            # std dev
            ix_std = xx_std.sel(month=months[m])
            ix_std = ix_std.to_array(name="stddev_" + m).drop("variable").squeeze()
            ix_std = ix_std.astype(np.float32)

            # count
            ix_count = xx_pq.sel(month=months[m])
            ix_count = ix_count.to_array(name="count_" + m).drop("variable").squeeze()
            ix_count = ix_count.astype(np.int16)

            # append da's to lists
            ndvi_var_mean.append(ix_mean)
            ndvi_var_std.append(ix_std)
            pq.append(ix_count)

        # merge them all into one dataset
        clim = xr.merge(ndvi_var_mean + ndvi_var_std + pq, compat="override").drop(
            "month"
        )

        return clim

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


register("ndvi_tools.ndvi_climatology_plugin", NDVIClimatology)
