# ndvi-anomalies

Production of Landsat resolution NDVI anomalies for the Africa continent

## Updating the pip requirements

Fix any requirement versions in `docker/fixed-requirements.txt`

Install `pip-compile` and then run `pip-compile --output-file=docker/requirements.txt production/ndvi_tools/setup.py docker/fixed-requirements.txt`.
