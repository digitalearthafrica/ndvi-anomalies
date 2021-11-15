ARG py_env_path=/env
ARG V_BASE=3.3.0

FROM opendatacube/geobase-builder:${V_BASE} as env_builder
ENV LC_ALL=C.UTF-8

# Install our Python requirements
COPY docker/requirements.txt docker/version.txt docker/constraints.txt /conf/

RUN cat /conf/version.txt && \
  env-build-tool new /conf/requirements.txt /conf/constraints.txt ${py_env_path}

# Install the ndvi-tools
ADD production/ndvi_tools /tmp/ndvi_tools
RUN /env/bin/pip install \
  --extra-index-url="https://packages.dea.ga.gov.au" /tmp/ndvi_tools && \
  rm -rf /tmp/ndvi_tools

# Below is the actual image that does the running
FROM opendatacube/geobase-runner:${V_BASE}
ARG py_env_path=/env

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="${py_env_path}/bin:${PATH}" \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install software-properties-common -y \
    && apt-get upgrade -y
    
# Add in the dask configuration
COPY docker/distributed.yaml /etc/dask/distributed.yaml
ADD docker/apt-run.txt /tmp/
RUN apt-get update \
    && sed 's/#.*//' /tmp/apt-run.txt | xargs apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
COPY --from=env_builder $py_env_path $py_env_path

RUN env && echo $PATH && pip freeze && pip check
