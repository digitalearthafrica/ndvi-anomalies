FROM osgeo/gdal:ubuntu-small-3.3.3

ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Add in the dask configuration
COPY docker/distributed.yaml /etc/dask/distributed.yaml

#ading in geojson extents
COPY testing/data/testing_extent.geojson /code/testing_extent.geojson
COPY testing/data/africa_land_extent.geojson /code/africa_land_extent.geojson

# Install system tools
RUN apt-get update \
    && apt-get install software-properties-common -y
    
ADD docker/apt-run.txt /conf/
RUN apt-get update \
    && sed 's/#.*//' /conf/apt-run.txt | xargs apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Install our Python requirements
COPY docker/requirements.txt docker/version.txt /conf/

RUN cat /conf/version.txt && \
    pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
    -r /conf/requirements.txt \
    --no-binary rasterio \
    --no-binary shapely \
    --no-binary fiona

# Install the ndvi-tools
ADD production/ndvi_tools /code
RUN pip install /code
WORKDIR /code

RUN pip freeze
