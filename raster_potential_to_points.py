#!/usr/bin/env python3
"""
Sample wet_woodland_potential.tif (0-1 restoration suitability) to points [lon, lat, value]
for deck.gl HeatmapLayer. Optionally filter by minimum suitability to keep full resolution
only where it matters (e.g. --min-value 0.5).
"""

import json
import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.crs import CRS


def main():
    parser = argparse.ArgumentParser(
        description="Convert potential raster to points [lon, lat, value] for HeatmapLayer"
    )
    parser.add_argument("--raster", default="data/wet_woodland_potential.tif", help="Input GeoTIFF (0-1 suitability)")
    parser.add_argument("--output", default="docs/potential_points.json", help="Output JSON path")
    parser.add_argument(
        "--min-value",
        type=float,
        default=None,
        metavar="0-1",
        help="Only output pixels with suitability >= this (e.g. 0.5). Enables full resolution for suitable areas.",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=1,
        help="Sample every Nth pixel (1=all). Ignored if --min-value is set (always step=1 when filtering).",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=500_000,
        help="Max points when not using --min-value (step is increased to stay under this).",
    )
    parser.add_argument(
        "--binary",
        action="store_true",
        help="Write .bin (12 bytes/point: lon, lat, value as float32) to stay under GitHub 100MB limit.",
    )
    args = parser.parse_args()

    raster_path = Path(args.raster)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}. Place wet_woodland_potential.tif there and re-run.")

    print(f"Reading: {raster_path}")
    with rasterio.open(raster_path) as src:
        nodata = src.nodata
        if nodata is None:
            nodata = np.nan

        dst_crs = CRS.from_epsg(4326)
        with WarpedVRT(src, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
            data = vrt.read(1)
            transform = vrt.transform
            h, w = data.shape

        valid = np.isfinite(data)
        if not (nodata is None or (isinstance(nodata, float) and np.isnan(nodata))):
            valid &= (data != nodata)

        # Normalize to 0-1
        if valid.any():
            vmin = float(np.nanmin(data[valid]))
            vmax = float(np.nanmax(data[valid]))
            if vmax > vmin:
                values = np.where(valid, np.clip((data - vmin) / (vmax - vmin), 0, 1), np.nan)
            else:
                values = np.where(valid, 0.5, np.nan)
        else:
            values = np.full_like(data, np.nan)

        use_min_value = args.min_value is not None
        if use_min_value:
            step = 1
            min_val = float(args.min_value)
            print(f"Filtering: only pixels with suitability >= {min_val}")
        else:
            step = args.step
            n_valid = int(np.sum(valid))
            if n_valid > 0:
                sampled = (h // step) * (w // step)
                while sampled > args.max_points and step < min(h, w):
                    step += 1
                    sampled = (h // step) * (w // step)
            if step > args.step:
                print(f"Step increased to {step} to stay under {args.max_points:,} points")

        points = []
        for row in range(0, h, step):
            for col in range(0, w, step):
                v = values[row, col]
                if not np.isfinite(v) or np.isnan(v):
                    continue
                if use_min_value and v < min_val:
                    continue
                lon, lat = transform * (col + 0.5, row + 0.5)
                points.append([round(lon, 6), round(lat, 6), round(float(v), 4)])

        print(f"Writing {len(points):,} points to {out_path}")
        if args.binary:
            out_path = out_path.with_suffix(".bin") if out_path.suffix == ".json" else out_path
            arr = np.array(points, dtype=np.float32)
            arr.tofile(out_path)
            print(f"Binary: {out_path.stat().st_size / (1024*1024):.1f} MB (12 bytes/point)")
        else:
            with open(out_path, "w") as f:
                json.dump(points, f, separators=(",", ":"))

    print("Done. Use potential_points.json (or .bin) with HeatmapLayer.")


if __name__ == "__main__":
    main()
