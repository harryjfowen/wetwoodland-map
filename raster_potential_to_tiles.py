#!/usr/bin/env python3
"""
Generate a raster tile pyramid from wet_woodland_potential.tif (0-1 suitability)
with the same 6-color scale. Outputs docs/potential_tiles/{z}/{x}/{y}.png for
deck.gl TileLayer (higher resolution as you zoom in).
Requires: rasterio, numpy, Pillow, GDAL (gdal2tiles.py).
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.crs import CRS

try:
    from PIL import Image
except ImportError:
    raise ImportError("Install Pillow: pip install Pillow")

COLOR_RANGE = [
    [1, 152, 189],
    [73, 227, 206],
    [216, 254, 181],
    [254, 237, 177],
    [254, 173, 84],
    [209, 55, 78],
]


def value_to_rgb(v):
    v = float(np.clip(v, 0, 1))
    n = len(COLOR_RANGE) - 1
    pos = v * n
    i = int(np.clip(np.floor(pos), 0, n - 1))
    j = min(i + 1, n)
    t = pos - i
    r = int(COLOR_RANGE[i][0] + (COLOR_RANGE[j][0] - COLOR_RANGE[i][0]) * t)
    g = int(COLOR_RANGE[i][1] + (COLOR_RANGE[j][1] - COLOR_RANGE[i][1]) * t)
    b = int(COLOR_RANGE[i][2] + (COLOR_RANGE[j][2] - COLOR_RANGE[i][2]) * t)
    return r, g, b


def main():
    parser = argparse.ArgumentParser(description="Generate raster tiles from potential TIF for TileLayer")
    parser.add_argument("--raster", default="data/wet_woodland_potential.tif", help="Input GeoTIFF")
    parser.add_argument("--output-dir", default="docs/potential_tiles", help="Output tile directory")
    parser.add_argument("--min-zoom", type=int, default=0, help="Min tile zoom")
    parser.add_argument("--max-zoom", type=int, default=12, help="Max tile zoom")
    parser.add_argument("--opacity", type=float, default=0.85, help="Alpha for colored pixels (0-1)")
    args = parser.parse_args()

    raster_path = Path(args.raster)
    out_dir = Path(args.output_dir)
    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}")

    print(f"Reading: {raster_path}")
    with rasterio.open(raster_path) as src:
        nodata = src.nodata
        if nodata is None:
            nodata = np.nan
        dst_crs = CRS.from_epsg(3857)
        with WarpedVRT(src, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
            data = vrt.read(1)
            transform = vrt.transform
            bounds_3857 = list(vrt.bounds)  # left, bottom, right, top
            width, height = vrt.width, vrt.height

        valid = np.isfinite(data)
        if not (nodata is None or (isinstance(nodata, float) and np.isnan(nodata))):
            valid &= (data != nodata)
        if valid.any():
            vmin = float(np.nanmin(data[valid]))
            vmax = float(np.nanmax(data[valid]))
            if vmax > vmin:
                norm = np.where(valid, np.clip((data - vmin) / (vmax - vmin), 0, 1), np.nan)
            else:
                norm = np.where(valid, 0.5, np.nan)
        else:
            norm = np.full_like(data, np.nan)

        h, w = norm.shape
        rgb = np.zeros((h, w, 4), dtype=np.uint8)
        for i in range(h):
            for j in range(w):
                v = norm[i, j]
                if np.isnan(v) or not np.isfinite(v):
                    rgb[i, j] = [0, 0, 0, 0]
                else:
                    r, g, b = value_to_rgb(v)
                    rgb[i, j] = [r, g, b, int(255 * args.opacity)]

        img = Image.fromarray(rgb[::-1], mode="RGBA")
        img_array = np.array(img)

    from rasterio.transform import from_bounds
    left, bottom, right, top = bounds_3857
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as f:
        temp_tif = f.name
    try:
        out_transform = from_bounds(left, bottom, right, top, width, height)
        # Rasterio row 0 = top (north); Image had row 0 = south, so flip
        out_array = img_array[::-1, :, :]
        with rasterio.open(
            temp_tif,
            "w",
            driver="GTiff",
            width=width,
            height=height,
            count=4,
            dtype=out_array.dtype,
            crs=dst_crs,
            transform=out_transform,
            nodata=0,
        ) as dst:
            dst.write(out_array[:, :, 0], 1)
            dst.write(out_array[:, :, 1], 2)
            dst.write(out_array[:, :, 2], 3)
            dst.write(out_array[:, :, 3], 4)

        gdal2tiles = "gdal2tiles.py"
        try:
            subprocess.run(["which", "gdal2tiles.py"], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            gdal2tiles = "gdal2tiles"
        cmd = [
            gdal2tiles,
            "-r", "near",
            "-z", f"{args.min_zoom}-{args.max_zoom}",
            "--processes=1",
            "--verbose",
            temp_tif,
            str(out_dir),
        ]
        print("Running:", " ".join(cmd))
        subprocess.run(cmd, check=True)
        print(f"Tiles written to {out_dir}")
    finally:
        Path(temp_tif).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
