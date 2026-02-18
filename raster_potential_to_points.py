#!/usr/bin/env python3
"""
Sample wet_woodland_potential.tif (0-1 restoration suitability) to points [lon, lat, value]
or [lon, lat, value, land_class] for deck.gl HeatmapLayer. Optionally burn land value class
(0=1-2, 1=3, 2=4-5) when --landvalue is provided.
"""

import json
import argparse
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
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
        help="Write .bin (12 or 16 bytes/point) to stay under GitHub 100MB limit.",
    )
    parser.add_argument(
        "--landvalue",
        default=None,
        metavar="RASTER",
        help="Land value class raster (0=1-2, 1=3, 2=4-5, 255=nodata). Same grid as potential. From landvalue_to_raster.py",
    )
    args = parser.parse_args()

    raster_path = Path(args.raster)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    use_landvalue = args.landvalue and Path(args.landvalue).exists()

    if not raster_path.exists():
        raise FileNotFoundError(f"Raster not found: {raster_path}. Place wet_woodland_potential.tif there and re-run.")

    print(f"Reading: {raster_path}")
    with rasterio.open(raster_path) as src:
        nodata = src.nodata
        if nodata is None:
            nodata = np.nan
        src_crs = src.crs
        src_transform = src.transform
        data = src.read(1)
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

        if use_landvalue:
            with rasterio.open(args.landvalue) as lv:
                if lv.shape != (h, w) or lv.transform != src_transform:
                    raise ValueError("Land value raster must match potential raster shape and transform.")
                lv_classes = lv.read(1)
                lv_nodata = lv.nodata if lv.nodata is not None else 255
            print(f"Land value classes from {args.landvalue} (0=1-2, 1=3, 2=4-5)")

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

        # Mask: valid suitability and optional filters
        mask = valid & np.isfinite(values)
        if use_min_value:
            mask &= (values >= min_val)
        if use_landvalue:
            mask &= (lv_classes >= 0) & (lv_classes <= 2) & (lv_classes != lv_nodata)

        # Apply step (when step>1, keep only rows/cols on the step grid)
        rows, cols = np.where(mask)
        if step > 1:
            step_ok = (rows % step == 0) & (cols % step == 0)
            rows, cols = rows[step_ok], cols[step_ok]

        n_pts = len(rows)
        if n_pts == 0:
            print("No points pass filters.")
            return

        # Pixel centers in source CRS (Affine: x = a*c + b*r + c, y = d*c + e*r + f)
        t = src_transform
        xs = t.a * (cols + 0.5) + t.b * (rows + 0.5) + t.c
        ys = t.d * (cols + 0.5) + t.e * (rows + 0.5) + t.f
        lons, lats = warp_transform(src_crs, CRS.from_epsg(4326), xs, ys)

        vals_pt = values[rows, cols].astype(np.float32)
        if use_landvalue:
            lcs_pt = lv_classes[rows, cols].astype(np.float32)

        print(f"Writing {n_pts:,} points to {out_path}")
        if args.binary:
            out_path = out_path.with_suffix(".bin") if out_path.suffix != ".bin" else out_path
            if use_landvalue:
                arr = np.column_stack([np.array(lons, dtype=np.float32), np.array(lats, dtype=np.float32), vals_pt, lcs_pt])
            else:
                arr = np.column_stack([np.array(lons, dtype=np.float32), np.array(lats, dtype=np.float32), vals_pt])
            arr.tofile(out_path)
            nbytes = 16 if use_landvalue else 12
            print(f"Binary: {out_path.stat().st_size / (1024*1024):.1f} MB ({nbytes} bytes/point)")
        else:
            if use_landvalue:
                points = [[round(lons[i], 6), round(lats[i], 6), round(float(vals_pt[i]), 4), float(lcs_pt[i])] for i in range(n_pts)]
            else:
                points = [[round(lons[i], 6), round(lats[i], 6), round(float(vals_pt[i]), 4)] for i in range(n_pts)]
            with open(out_path, "w") as f:
                json.dump(points, f, separators=(",", ":"))

    print("Done. Use potential_points.json (or .bin) with HeatmapLayer.")


if __name__ == "__main__":
    main()
