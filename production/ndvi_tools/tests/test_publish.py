import pytest
from pathlib import Path

from odc.dscache import DatasetCache

from datacube.utils.geometry import Geometry

from ndvi_tools.geojson_defined_tasks import filter_tiles, publish_tasks, get_geometry

import boto3
import moto

TEST_DATA_FOLDER = Path(__file__).parent / "data"


def test_geojson(test_geom):
    geometry = get_geometry(test_geom)
    assert type(geometry) == Geometry


def test_partition_area(test_db):
    dataset_cache = DatasetCache.open_ro(str(test_db))

    tiles = dataset_cache.tiles("africa_30")
    assert len(tiles) == 111

    # Filter to tiles that are in the NDVI Climatology product
    filtered = list(filter_tiles(dataset_cache))
    assert len(filtered) == 89

    tiles = dataset_cache.tiles("africa_30")
    # Filter tiles that are in the NDVI Climatology product limiting to only 10
    filtered = list(filter_tiles(dataset_cache, limit=10))
    assert len(filtered) == 10


@moto.mock_sqs
def test_publish_sns(test_db):
    dataset_cache = DatasetCache.open_ro(str(test_db))

    # Create an SQS queue
    sqs = boto3.resource("sqs", region_name="us-east-1")
    queue = sqs.create_queue(QueueName="test-queue")
    publish_tasks(dataset_cache, queue, "s3://test-files/test.db")


@pytest.fixture
def test_geom():
    return TEST_DATA_FOLDER / "testing_extent.geojson"


@pytest.fixture
def test_db():
    return TEST_DATA_FOLDER / "test.db"
