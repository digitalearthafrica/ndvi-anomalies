from functools import partial
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

import datacube
import numpy as np
import pandas as pd
import xarray as xr
from datacube.model import Dataset
from datacube.utils import masking
from datacube.utils.geometry import GeoBox, assign_crs
from odc.algo import enum_to_bool, erase_bad, keep_good_only, to_float
from odc.algo._masking import _first_valid_np, _fuse_or_np, _xr_fuse, mask_cleanup
from odc.algo.io import load_with_native_transform
from odc.stats.plugins import StatsPluginInterface
from odc.stats.plugins._registry import register
from toolz import get_in


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
        nodata_flags_s2: Optional[Sequence[str]] = ["no data"],
        mask_filters: Optional[Iterable[Tuple[str, int]]] = [
            ["opening", 5],
            ["dilation", 5],
        ],
        rolling_window: int = 3,
        min_num_obs: int = 20,
        wofs_threshold: float = 0.85,
        work_chunks: Dict[str, Optional[Any]] = dict(x=1600, y=1600),
        scale: float = 0.0000275,
        offset: float = -0.2,
        output_dtype: str = "float32",
        output_bands: Tuple[str, ...] = (
            "ndvi_mean",
            "ndvi_std_anomaly",
            "clear_count",
        ),
        **kwargs,
    ):

        self.bands_ls89 = bands_ls89
        self.bands_s2 = bands_s2
        self.output_bands = output_bands
        self.mask_band_ls89 = mask_band_ls89
        self.mask_band_s2 = mask_band_s2
        self.rolling_window = rolling_window
        self.min_num_obs = min_num_obs
        self.wofs_threshold = wofs_threshold
        self.group_by = group_by
        self.input_bands_ls89 = tuple(bands_ls89) + (mask_band_ls89,)
        self.input_bands_s2 = tuple(bands_s2) + (mask_band_s2,)
        self.flags_ls89 = flags_ls89
        self.flags_s2 = flags_s2
        self.resampling = resampling
        self.nodata_flags_ls89 = nodata_flags_ls89
        self.nodata_flags_s2 = nodata_flags_s2
        self.mask_filters = mask_filters
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
            )  # combine with cloud mask

            # set no_data bitmask - True=data, False=no-data
            nodata_mask, _ = masking.create_mask_value(
                flags_def, **self.nodata_flags_ls89
            )
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

            # Create cloud etc mask
            mask_band = xx[self.mask_band_s2]
            xx = xx.drop_vars([self.mask_band_s2])
            pq_mask = enum_to_bool(mask=mask_band, categories=self.flags_s2)

            # Erase nodata pixels
            keeps = enum_to_bool(
                mask=mask_band, categories=self.nodata_flags_s2, invert=True
            )
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

        # Separate out LS89 datasets from s2
        ls_dss = []
        if "ls8_sr" in product_dss:
            ls_dss = ls_dss + product_dss["ls8_sr"]

        if "ls9_sr" in product_dss:
            ls_dss = ls_dss + product_dss["ls9_sr"]

        products = {}
        # load landsat 8/9.
        if len(ls_dss) > 0:
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
            products["ls89"] = ls89

        # load s2
        if "s2_l2a" in product_dss:
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
            products["s2"] = s2

        # Loop through products, rescale to SR, calculate NDVI
        for key, datasets in products.items():
            # seperate pq layers
            cloud_mask = datasets["cloud_mask"]

            # Morphological operators on cloud layer to improve it
            if self.mask_filters is not None:
                cloud_mask = mask_cleanup(cloud_mask, mask_filters=self.mask_filters)

            # erase pixels with dilated cloud
            datasets = datasets.drop_vars(["cloud_mask"])
            datasets = erase_bad(datasets, cloud_mask)

            # rescale bands into surface reflectance scale if product is Landsat 8/9
            if key == "ls89":
                for band in datasets.data_vars.keys():
                    # set nodata_mask - use for resetting nodata pixel after rescale
                    nodata_mask = datasets[band] == datasets[band].attrs.get("nodata")
                    # rescale
                    datasets[band] = self.scale * datasets[band] + self.offset
                    #  apply nodata_mask - reset nodata pixels to output-nodata
                    datasets[band] = datasets[band].where(~nodata_mask, self.output_nodata)
                    # set data-type and nodata attrs
                    datasets[band] = datasets[band].astype(self.output_dtype)
                    datasets[band].attrs["nodata"] = self.output_nodata

            # Rename s2 nir_2 to make ndvi calc easy, then convert s2 to float
            # so nodata/masked regions are set to NaN
            if key == "s2":
                datasets = datasets.rename({"nir_2": "nir"})
                datasets = to_float(datasets, dtype=self.output_dtype)

            # calculate ndvi
            datasets["ndvi"] = (datasets.nir - datasets.red) / (datasets.nir + datasets.red)

            # remove remaining SR bands
            datasets = datasets.drop_vars(["red", "nir"])

        # combine data arrays
        ndvi = xr.concat([d for d in products.values()], dim="spec").sortby("spec")

        # Remove NDVI's that aren't between 0 and 1
        ndvi = ndvi.where((ndvi >= 0) & (ndvi <= 1))

        return ndvi

    def reduce(self, xx: xr.Dataset) -> xr.Dataset:
        """ """
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

        # find the month and year we've loaded from time dim,
        # this is used to load the right month from ndvi-clim
        # and to append time dimension to output
        m = xx.spec["time"].dt.month.values[0]
        y = str(xx.spec["time"].dt.year.values[0])
        time = pd.date_range(np.datetime64(y + "-" + f"{m:02d}"), periods=1, freq="M")

        # get month we're loading as abbreviated str
        month = list(months.keys())[list(months.values()).index(m)]

        # hard-code loading of ndvi_climatology_ls as doesn't
        # fit with odc-stat save-tasks paradigm
        dc = datacube.Datacube(app="Vegetation_anomalies")
        ndvi_clim = (
            dc.load(
                product="ndvi_climatology_ls",
                like=xx.geobox,
                measurements=["mean_" + month, "stddev_" + month, "count_" + month],
                dask_chunks=self.work_chunks,
                resampling=self.resampling,
            )
            .squeeze()
            .drop("time")
        )  # Remove time dimension

        # --Make a quality assurance mask where clear observation count is low
        #  in the ndvi-climatology product ----
        qa_mask = ndvi_clim["count_" + month] >= self.min_num_obs

        # remove pixels where obs are < min_num_obs
        ndvi_clim = ndvi_clim.where(qa_mask)

        # calculate the mean NDVI for the month
        xx_mean = xx.mean("spec")

        # calculate anomaly
        anomalies = xr.apply_ufunc(
            lambda x, m, s: (x - m) / s,
            xx_mean,
            ndvi_clim["mean_" + month],
            ndvi_clim["stddev_" + month],
            output_dtypes=[xx.ndvi.dtype],
            dask="allowed",
        )

        # rename arrays, add time dim
        anomalies = (
            anomalies.to_array(name="ndvi_std_anomaly").drop("variable").squeeze()
        )
        anomalies = anomalies.expand_dims(time=time)
        anomalies = assign_crs(anomalies, crs="epsg:6933")  # add geobox

        xx_mean = xx_mean.to_array(name="ndvi_mean").drop("variable").squeeze()
        xx_mean = xx_mean.expand_dims(time=time)

        xx_pq = xx_pq.to_array(name="clear_count").drop("variable").squeeze()
        xx_pq = xx_pq.expand_dims(time=time)

        # merge them all into one dataset
        anom = xr.merge([xx_mean, anomalies, xx_pq], compat="override")
        anom = assign_crs(anom, crs="epsg:6933")  # Add geobox

        # --mask with all-time WOfS to remove permanent waterbodies---
        wofs = dc.load(
            product="wofs_ls_summary_alltime",
            measurements=["frequency"],
            like=xx.geobox,
            dask_chunks=self.work_chunks,
        ).frequency.squeeze()

        # set masked terrain regions to 0
        wofs = xr.where(xr.ufuncs.isnan(wofs), 0, wofs)

        # threshold to create waterbodies mask
        wofs = wofs < self.wofs_threshold

        # mask
        anom = anom.where(wofs)

        # enforce dtypes (masking auto-changes to float64)
        anom["ndvi_std_anomaly"] = anom["ndvi_std_anomaly"].astype(np.float32)
        anom["ndvi_mean"] = anom["ndvi_mean"].astype(np.float32)
        anom["clear_count"] = anom["clear_count"].astype(np.int8)

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
