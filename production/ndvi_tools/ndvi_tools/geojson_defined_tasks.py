from distutils.log import debug
import json
import fsspec
import click
import toolz
from datacube.utils.geometry import Geometry
from odc.aws.queue import get_queue, publish_messages
from odc.stats.tasks import render_sqs
from odc.dscache import DatasetCache

from odc.dscache.tools.tiling import GRIDS


def get_geometry(geojson_file: str) -> Geometry:
    with fsspec.open(geojson_file) as f:
        data = json.load(f)

    return Geometry(
        data["features"][0]["geometry"], crs=data["crs"]["properties"]["name"]
    )


def filter_tiles(dataset_cache: DatasetCache, geometry: Geometry):
    tiles = dataset_cache.tiles("africa_30")
    for tile in tiles:
        tile_geometry = GRIDS["africa_30"].tile_geobox((tile[0][1], tile[0][2])).extent
        if tile_geometry.intersects(geometry):
            yield tile


def publish_tasks(
    dataset_cache: DatasetCache, geometry: Geometry, queue, remote_db_file: str, dry_run: bool = False
):
    messages = []

    tiles = filter_tiles(dataset_cache, geometry)
    for n, tile in enumerate(tiles):
        tile, _ = tile
        message = dict(Id=str(n), MessageBody=json.dumps(render_sqs(tile, remote_db_file)))
        messages.append(message)

    if not dry_run:
        for bunch in toolz.partition_all(10, messages):
            publish_messages(queue, bunch)
        print(f"Published {len(messages)} messages")
    else:
        print(f"DRYRUN! Would have published {len(messages)} messages")


@click.command("ndvi-task")
@click.argument("geojson_file", type=str)
@click.argument("db_file", type=str)
@click.argument("remote_db_file", type=str)
@click.argument("queue_name", type=str)
@click.option("--dry-run", is_flag=True, default=False)
def main(geojson_file, db_file, remote_db_file, queue_name, dry_run):
    geometry = get_geometry(geojson_file)
    queue = get_queue(queue_name)
    dataset_cache = DatasetCache.open_ro(db_file)

    publish_tasks(dataset_cache, geometry, queue, remote_db_file, dry_run=dry_run)


if __name__ == "__main__":
    main()
