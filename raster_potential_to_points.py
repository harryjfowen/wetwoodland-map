#!/usr/bin/env python3
"""
Sample wet_woodland_potential.tif (0-1 restoration suitability) to points [lon, lat, value]
for deck.gl HeatmapLayer. Subsamples the raster to keep JSON size reasonable.
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
        "--step",
        type=int,
        default=1,
        help="Sample every Nth pixel (1=all, 2=half, 10=sparse). Increase to reduce file size.",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=500_000,
        help="Max points to output (if step=1 would exceed this, step is increased)",
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

        # Decide step so we don't exceed max_points
        step = args.step
        n_valid = int(np.sum(valid))
        if n_valid > 0:
            # if we sample every `step` pixel, we get ~ n_valid / (step*step) points (2D)
            # rough: total pixels = h*w, sampled = (h//step)*(w//step)
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
                # Pixel center in pixel coords
                lon, lat = transform * (col + 0.5, row + 0.5)
                points.append([round(lon, 6), round(lat, 6), round(float(v), 4)])

        print(f"Writing {len(points):,} points to {out_path}")
        with open(out_path, "w") as f:
            json.dump(points, f, separators=(",", ":"))

    print("Done. Use potential_points.json with HeatmapLayer.")


if __name__ == "__main__":
    main()
