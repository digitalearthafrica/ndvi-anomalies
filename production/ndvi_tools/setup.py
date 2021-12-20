#!/usr/bin/env python3

import io
import os
from setuptools import find_packages, setup

# What packages are required for this module to be executed?
REQUIRED = [
    "datacube",
    "numpy",
    "odc-algo",
    "odc-stats",
    "odc-dscache",
    "toolz",
    "xarray",
    "fsspec",
    "pandas"
]

# Package meta-data.
NAME = "ndvi_tools"
DESCRIPTION = "Tools for running DE Africa's NDVI anomaly project"
URL = "https://github.com/digitalearthafrica/deafrica-sandbox-notebooks"
EMAIL = "chad.burton@ga.gov.au"
AUTHOR = "Digital Earth Africa"
REQUIRES_PYTHON = ">=3.6.0"

# Import the README and use it as the long-description.
here = os.path.abspath(os.path.dirname(__file__))

try:
    with io.open(os.path.join(here, "README.md"), encoding="utf-8") as f:
        long_description = "\n" + f.read()
except FileNotFoundError:
    long_description = DESCRIPTION

setup_kwargs = {
    "name": NAME,
    "version": "1.0.0",
    "description": DESCRIPTION,
    "long_description": long_description,
    "author": AUTHOR,
    "author_email": EMAIL,
    "python_requires": REQUIRES_PYTHON,
    "url": URL,
    "install_requires": REQUIRED,
    "packages": find_packages(),
    "include_package_data": True,
    "license": "Apache License 2.0",
    "entry_points": {
        "console_scripts": [
            "cm-task = ndvi_tools.geojson_defined_tasks:main"]
    },
}

setup(**setup_kwargs)
