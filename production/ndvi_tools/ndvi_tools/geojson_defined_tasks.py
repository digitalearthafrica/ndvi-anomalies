import json
from pathlib import Path
from typing import Optional

import click
import fsspec
import pandas as pd
import toolz
from datacube.utils.geometry import Geometry
from odc.aws.queue import get_queue, publish_messages
from odc.dscache import DatasetCache
from odc.stats.tasks import render_sqs

# Load the ndvi_clim.csv from the relative path
here = Path(__file__).parent
ALL_TILES = set(pd.read_csv(here / "ndvi_clim.csv")["region_code"])


def get_geometry(geojson_file: str) -> Geometry:
    with fsspec.open(geojson_file) as f:
        data = json.load(f)

    return Geometry(
        data["features"][0]["geometry"], crs=data["crs"]["properties"]["name"]
    )


def filter_tiles(dataset_cache: DatasetCache, limit: Optional[int] = None):
    tiles = dataset_cache.tiles("africa_30")
    count = 0

    for tile in tiles:
        tile_id = f"x{tile[0][1]:03d}y{tile[0][2]:03d}"

        if tile_id in ALL_TILES:
            count += 1
            yield tile

            if limit is not None and count >= limit:
                break


def publish_tasks(
    dataset_cache: DatasetCache,
    queue,
    remote_db_file: str,
    dry_run: bool = False,
    limit: Optional[int] = None,
):
    messages = []

    tiles = filter_tiles(dataset_cache, limit=limit)
    for n, tile in enumerate(tiles):
        tile, _ = tile
        message = dict(
            Id=str(n), MessageBody=json.dumps(render_sqs(tile, remote_db_file))
        )
        messages.append(message)

    if not dry_run:
        for bunch in toolz.partition_all(10, messages):
            publish_messages(queue, bunch)
        print(f"Published {len(messages)} messages")
    else:
        print(f"DRYRUN! Would have published {len(messages)} messages")


@click.command("ndvi-task")
@click.argument("db_file", type=str)
@click.argument("remote_db_file", type=str)
@click.argument("queue_name", type=str)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--limit", type=int, default=None)
def main(db_file, remote_db_file, queue_name, dry_run, limit):
    queue = get_queue(queue_name)
    dataset_cache = DatasetCache.open_ro(db_file)

    publish_tasks(dataset_cache, queue, remote_db_file, dry_run=dry_run, limit=limit)


if __name__ == "__main__":
    main()
