<img align="centre" src="figs/Github_banner.jpg" width="101%">

# Digital Earth Africa Continental NDVI Standardised Anomalies

## Background

Standardised NDVI Anomalies provide a measure of the vegetation health relative to long term average conditions by measuring the departure, in units of standard devaiations, away from the long-term average. These indices can be used to monitor areas where vegetation may be stressed, and as a proxy to detect potential drought. Negative values represent a reduction from normal NDVI, while positive values represent an increase from normal.

## Description

The Standardized NDVI Anomaly will have the following specifications:

* NDVI 'climatologies' are developed using harmonsized Landsat 5,7,and 8 satellite imagery from the years 1984 to 2020
* Anomalies will have monthly temporal frequency
* All datasets will have a spatial resolution of 30 metres

## Updating the pip requirements

Fix any requirement versions in `docker/fixed-requirements.txt`

Install `pip-tools` and then run `pip-compile --output-file=docker/requirements.txt production/ndvi_tools/setup.py docker/fixed-requirements.txt`.


## Additional information

**License:** The code in this notebook is licensed under the [Apache License, Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).
Digital Earth Africa data is licensed under the [Creative Commons by Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) license.

**Contact:** If you need assistance, please post a question on the [Open Data Cube Slack channel](http://slack.opendatacube.org/) or on the [GIS Stack Exchange](https://gis.stackexchange.com/questions/ask?tags=open-data-cube) using the `open-data-cube` tag (you can view previously asked questions [here](https://gis.stackexchange.com/questions/tagged/open-data-cube)).
If you would like to report an issue with this notebook, you can file one on [Github](https://github.com/digitalearthafrica/crop-mask/issues).

