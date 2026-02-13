#!/usr/bin/env python3
"""
Convert wet_woodland_potential.tif (0-1 restoration suitability) to a web-ready PNG
with the same 6-color scale as the density map, plus a bounds JSON for deck.gl BitmapLayer.
"""

import json
import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.crs import CRS


# Same 6-color gradient as density map (cyan → red)
COLOR_RANGE = [
    [1, 152, 189],
    [73, 227, 206],
    [216, 254, 181],
    [254, 237, 177],
    [254, 173, 84],
    [209, 55, 78],
]


def value_to_rgb(v):
    """Map value in [0, 1] to RGB using COLOR_RANGE."""
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
    parser = argparse.ArgumentParser(description="Convert potential raster to PNG + bounds for web map")
    parser.add_argument("--raster", default="data/wet_woodland_potential.tif", help="Input GeoTIFF (0-1 suitability)")
    parser.add_argument("--output-dir", default="docs", help="Output directory for PNG and bounds JSON")
    parser.add_argument("--width", type=int, default=1200, help="Output image width (pixels)")
    parser.add_argument("--opacity", type=float, default=0.85, help="Opacity of colored pixels (0-1)")
    args = parser.parse_args()

    raster_path = Path(args.raster)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / "potential.png"
    bounds_path = out_dir / "potential_bounds.json"

    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}. Place wet_woodland_potential.tif there and re-run.")

    print(f"Reading: {raster_path}")
    with rasterio.open(raster_path) as src:
        data = src.read(1)
        nodata = src.nodata
        if nodata is None:
            nodata = np.nan

        # Reproject to WGS84 and resample to target width
        dst_crs = CRS.from_epsg(4326)
        height_out = int(data.shape[0] * (args.width / data.shape[1]))
        with WarpedVRT(
            src,
            crs=dst_crs,
            width=args.width,
            height=height_out,
            resampling=Resampling.bilinear,
        ) as vrt:
            reproj = vrt.read(1)
            bounds_wgs84 = list(vrt.bounds)  # left, bottom, right, top

        # Valid mask and normalize to 0-1 (data may already be 0-1 from MaxEnt)
        valid_r = np.isfinite(reproj)
        if not (nodata is None or (isinstance(nodata, float) and np.isnan(nodata))):
            valid_r &= (reproj != nodata)
        if valid_r.any():
            vmin_r = float(np.nanmin(reproj[valid_r]))
            vmax_r = float(np.nanmax(reproj[valid_r]))
            if vmax_r > vmin_r:
                norm = np.where(valid_r, np.clip((reproj - vmin_r) / (vmax_r - vmin_r), 0, 1), np.nan)
            else:
                norm = np.where(valid_r, 0.5, np.nan)
        else:
            norm = np.full(reproj.shape, np.nan)

        # Build RGBA image (same palette, alpha by opacity and validity)
        h, w = norm.shape
        rgb = np.zeros((h, w, 4), dtype=np.uint8)
        for i in range(h):
            for j in range(w):
                v = norm[i, j]
                if np.isnan(v) or (not np.isfinite(v)):
                    rgb[i, j] = [0, 0, 0, 0]
                else:
                    r, g, b = value_to_rgb(v)
                    rgb[i, j] = [r, g, b, int(255 * args.opacity)]

        # PNG: flip so row 0 is top (image convention)
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("Install Pillow: pip install Pillow")
        img = Image.fromarray(rgb[::-1], mode="RGBA")
        img.save(png_path, "PNG")
        print(f"Wrote: {png_path}")

    # Bounds for deck.gl BitmapLayer: [minX, minY, maxX, maxY] = [west, south, east, north]
    bounds_list = [bounds_wgs84[0], bounds_wgs84[1], bounds_wgs84[2], bounds_wgs84[3]]
    with open(bounds_path, "w") as f:
        json.dump(bounds_list, f)
    print(f"Wrote: {bounds_path}")
    print("Done. Add potential.png and potential_bounds.json to docs/ and use the Potential tab.")


if __name__ == "__main__":
    main()
