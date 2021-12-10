<img align="centre" src="figs/Github_banner.jpg" width="101%">

# Digital Earth Africa Continental NDVI Anomalies

## Background

Production of Landsat resolution NDVI standardised anomalies for the Africa continent.  Standadised NDVI Anomalies provide alternative measures of the relative vegetation health. These indices can be used to monitor the areas where vegetation may be stressed, and as a proxy to detect potential drought.

## Description

The Standardized NDVI Anomaly will have the following specifications:

* Developed using Landsat 5,7,and 8 satellite imagery
* Monthly temporal frequency
* Have a spatial resolution of 30 metres
* Monthly NDVI climatologies are based on data from 1985 to 2020

## Updating the pip requirements

Fix any requirement versions in `docker/fixed-requirements.txt`

Install `pip-compile` and then run `pip-compile --output-file=docker/requirements.txt production/ndvi_tools/setup.py docker/fixed-requirements.txt`.


## Additional information

**License:** The code in this notebook is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
Digital Earth Africa data is licensed under the [Creative Commons by Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) license.

**Contact:** If you need assistance, please post a question on the [Open Data Cube Slack channel](http://slack.opendatacube.org/) or on the [GIS Stack Exchange](https://gis.stackexchange.com/questions/ask?tags=open-data-cube) using the `open-data-cube` tag (you can view previously asked questions [here](https://gis.stackexchange.com/questions/tagged/open-data-cube)).
If you would like to report an issue with this notebook, you can file one on [Github](https://github.com/digitalearthafrica/crop-mask/issues).

