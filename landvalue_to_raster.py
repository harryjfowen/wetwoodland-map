#!/usr/bin/env python3
"""
Dissolve land value shapefile into 3 groups (1-2, 3, 4-5) and rasterize to the same
grid as the potential raster. Output: landvalue_classes.tif (byte: 0=1-2, 1=3, 2=4-5, 255=nodata).
Requires: ogr2ogr (GDAL), rasterio, numpy. Run from repo root.
"""

import json
import subprocess
import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.crs import CRS


def main():
    parser = argparse.ArgumentParser(description="Dissolve land value into 3 groups and rasterize to potential grid")
    parser.add_argument("--landvalue-shp", default="data/landvalue.shp", help="Land value shapefile")
    parser.add_argument("--potential-raster", default="data/wet_woodland_potential.tif", help="Reference raster (grid/CRS)")
    parser.add_argument("--output", default="data/landvalue_classes.tif", help="Output class raster")
    args = parser.parse_args()

    shp = Path(args.landvalue_shp)
    ref_raster = Path(args.potential_raster)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data_dir = shp.parent

    if not shp.exists():
        raise FileNotFoundError(f"Shapefile not found: {shp}")
    if not ref_raster.exists():
        raise FileNotFoundError(f"Reference raster not found: {ref_raster}")

    # Dissolve with ogr2ogr (SQLite dialect for ST_Union)
    for name, where, out_name in [
        ("1-2", "alc_grade IN ('Grade 1','Grade 2')", "landvalue_group_12"),
        ("3", "alc_grade = 'Grade 3'", "landvalue_group_3"),
        ("4-5", "alc_grade IN ('Grade 4','Grade 5')", "landvalue_group_45"),
    ]:
        geojson_path = data_dir / f"{out_name}.json"
        if not geojson_path.exists():
            subprocess.run([
                "ogr2ogr", "-f", "GeoJSON", "-dialect", "sqlite",
                "-sql", f"SELECT ST_Union(geometry) as geometry FROM landvalue WHERE {where}",
                str(geojson_path), str(shp)
            ], check=True, capture_output=True)
        print(f"Dissolved {name} -> {geojson_path.name}")

    # Load geometries and rasterize to reference grid
    with rasterio.open(ref_raster) as ref:
        transform = ref.transform
        out_shape = ref.shape
        crs = ref.crs

    shapes_values = []
    for i, out_name in enumerate(["landvalue_group_12", "landvalue_group_3", "landvalue_group_45"]):
        geojson_path = data_dir / f"{out_name}.json"
        with open(geojson_path) as f:
            fc = json.load(f)
        if fc.get("features"):
            geom = fc["features"][0]["geometry"]
            shapes_values.append((geom, i))  # 0, 1, 2

    out_array = rasterize(
        shapes_values,
        out_shape=out_shape,
        transform=transform,
        fill=255,
        dtype=np.uint8,
        all_touched=True,
    )

    with rasterio.open(
        out_path, "w",
        driver="GTiff",
        width=out_array.shape[1],
        height=out_array.shape[0],
        count=1,
        dtype=out_array.dtype,
        crs=crs,
        transform=transform,
        nodata=255,
    ) as dst:
        dst.write(out_array, 1)

    print(f"Wrote {out_path} (0=1-2, 1=3, 2=4-5, 255=nodata)")


if __name__ == "__main__":
    main()
