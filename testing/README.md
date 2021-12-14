<img align="centre" src="../figs/Github_banner.jpg" width="101%">

# Digital Earth Africa Continental Testing Folder

### Background 

Landsat satellites have the longest temporal record of earth observations data, from landsat 5, 7 and 8. Ideally, the Landsat data record should be consistent over the Landsat sensor series, but that's not being the case Landsat-8 Operational Land Imager (OLI) has improved calibration than the previous Landsat-7 Enhanced Thematic Mapper (ETM +). To calibrate the two sensors sample collection points are taken across the Africa continent. These points will aid in the harmonising landsat 7 and 8.


This sections focuses 

* Continental data collection for harmonizing ARD Landsat 5-7 with Landsat 8
* Determining the coefficients for ndvi Harmonization of the Landsat collection 2
* Testing of the Harmonization Equation on the Landsat collection 2


### Below give a Summary of each notebook

1. HL87_continental_data_collection
    
    This notebook oulines the process of collection training samples across the africa continent using  `collect_training_data` function.
    
    
2. HL8L7_harmonization
    
    This notebooks generates the cooefficeient values for landsat 5 and landsat 7 NDVI to make it harmonise with Landsat  The slope, intercept and MAE are derived and the results are plotted out.

3. HL8L7_timeseries

    This notebook plots time series analysis of selected regions before and after applying the ndvi coefficient to landsat 5 and 7 to harmonize with Landsat 8.

4. Vegetation_anomalies_seasonal

    This notebook calculate seasonal _standardised_ NDVI anomalies with the harmonization of the landsat for any given season and year. The long-term seasonal climatologies (both mean and standard deviation) are calculated on-the-fly.
        


5. Vegetation_anomalies_monthly

     This notebook calculate monthly _standardised_ NDVI anomalies with the harmonization of the landsat for any given month and year. The long-term seasonal climatologies (both mean and standard deviation) are calculated on-the-fly.
        





## Additional information

**License:** The code in this notebook is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
Digital Earth Africa data is licensed under the [Creative Commons by Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) license.

**Contact:** If you need assistance, please post a question on the [Open Data Cube Slack channel](http://slack.opendatacube.org/) or on the [GIS Stack Exchange](https://gis.stackexchange.com/questions/ask?tags=open-data-cube) using the `open-data-cube` tag (you can view previously asked questions [here](https://gis.stackexchange.com/questions/tagged/open-data-cube)).
If you would like to report an issue with this notebook, you can file one on [Github](https://github.com/digitalearthafrica/crop-mask/issues).

