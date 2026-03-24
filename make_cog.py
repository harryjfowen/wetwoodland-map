#!/usr/bin/env python3
"""
Build Cloud-Optimised GeoTIFFs (EPSG:3857, uint8, DEFLATE) for deck.gl-raster.

Outputs:
  docs/wetwoodland_probability.cog.bin   — band 1 of wet_woodland_potential.tif
  docs/wetwoodland_extent_b2.cog.bin     — band 2 of wetwoodland_extent.tif

Usage:
  python make_cog.py                   # build both
  python make_cog.py --only extent     # build only extent band 2
  python make_cog.py --overwrite       # force rebuild
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

EPSG_3857 = "EPSG:3857"
TILE_SIZE = 512
NODATA_UINT8 = 255

# ── rasters to build ──────────────────────────────────────────────────────────
TARGETS = {
    "probability": {
        "src": "data/wet_woodland_potential.tif",
        "band": 1,
        "out": "docs/wetwoodland_probability.cog.bin",
        "resolution": 30,
        "resampling": Resampling.nearest,
    },
    "probability_coarse": {
        "src": "data/wet_woodland_potential.tif",
        "band": 1,
        "out": "docs/wetwoodland_probability_1km.cog.bin",
        "resolution": 1000,
        "resampling": Resampling.average,
    },
    "extent": {
        "src": "data/wetwoodland_extent.tif",
        "band": 2,
        "out": "docs/wetwoodland_extent_b2.cog.bin",
        "resolution": None,
        "resampling": Resampling.nearest,
    },
}

OVERVIEW_FACTORS = [2, 4, 8, 16, 32, 64, 128]


def warp_band_to_3857(
    src_path: Path,
    band: int,
    dst_path: Path,
    resolution: float | None = None,
    resampling: Resampling = Resampling.nearest,
) -> None:
    """Reproject a single band to EPSG:3857, write float32 GeoTIFF."""
    with rasterio.open(src_path) as src:
        src_nodata = src.nodata
        transform, width, height = calculate_default_transform(
            src.crs, EPSG_3857, src.width, src.height, *src.bounds, resolution=resolution
        )
        profile = src.profile.copy()
        profile.update(
            crs=EPSG_3857,
            transform=transform,
            width=width,
            height=height,
            count=1,
            dtype="float32",
            nodata=src_nodata,
            compress="DEFLATE",
            predictor=2,
            zlevel=9,
            tiled=True,
            blockxsize=TILE_SIZE,
            blockysize=TILE_SIZE,
        )
        with rasterio.open(dst_path, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, band),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                src_nodata=src_nodata,
                dst_transform=transform,
                dst_crs=EPSG_3857,
                dst_nodata=src_nodata,
                resampling=resampling,
            )


def quantize_to_uint8(src_path: Path, dst_path: Path) -> None:
    """
    Quantize float32 0-1 → uint8 1-254  (0 = transparent, 255 = nodata).
    Writes a tiled DEFLATE GeoTIFF ready to receive overviews.
    """
    with rasterio.open(src_path) as src:
        src_nodata = src.nodata
        profile = src.profile.copy()
        profile.update(
            dtype="uint8",
            nodata=NODATA_UINT8,
            compress="DEFLATE",
            predictor=2,
            zlevel=9,
            tiled=True,
            blockxsize=TILE_SIZE,
            blockysize=TILE_SIZE,
        )
        with rasterio.open(dst_path, "w", **profile) as dst:
            for _, window in src.block_windows(1):
                data = src.read(1, window=window).astype(np.float32)
                valid = np.isfinite(data)
                if src_nodata is not None:
                    valid &= data != float(src_nodata)
                out = np.full(data.shape, NODATA_UINT8, dtype=np.uint8)
                out[valid] = np.clip(
                    np.round(data[valid] * 254.0).astype(np.int32), 1, 254
                ).astype(np.uint8)
                dst.write(out, 1, window=window)


def add_overviews(path: Path) -> None:
    """Build internal overviews with nearest sampling to preserve nodata edges."""
    with rasterio.open(path, "r+") as ds:
        ds.build_overviews(OVERVIEW_FACTORS, Resampling.nearest)
        ds.update_tags(ns="rio_overview", resampling="nearest")


def write_cog(src_path: Path, dst_path: Path) -> None:
    """Copy internal-overview file to a proper COG layout."""
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as src:
        profile = src.profile.copy()
        profile.update(
            compress="DEFLATE",
            predictor=2,
            zlevel=9,
            tiled=True,
            blockxsize=TILE_SIZE,
            blockysize=TILE_SIZE,
            copy_src_overviews=True,
        )
        with rasterio.open(dst_path, "w", **profile) as dst:
            dst.write(src.read())
            # copy overview data
            for i in src.overviews(1):
                pass  # overviews are copied via copy_src_overviews


def build(name: str, overwrite: bool = False) -> None:
    cfg = TARGETS[name]
    src_path = Path(cfg["src"])
    out_path = Path(cfg["out"])

    if out_path.exists() and not overwrite:
        print(f"[{name}] {out_path} exists — skipping (use --overwrite to rebuild)")
        return

    if not src_path.exists():
        raise FileNotFoundError(f"Source raster not found: {src_path}")

    print(f"[{name}] Warping band {cfg['band']} to EPSG:3857 …")
    with tempfile.TemporaryDirectory(prefix="make_cog_") as tmp:
        tmp = Path(tmp)
        warped = tmp / "warped.tif"
        quantized = tmp / "quantized.tif"

        warp_band_to_3857(
            src_path,
            cfg["band"],
            warped,
            resolution=cfg.get("resolution"),
            resampling=cfg.get("resampling", Resampling.nearest),
        )

        print(f"[{name}] Quantizing to uint8 …")
        quantize_to_uint8(warped, quantized)

        print(f"[{name}] Building overviews …")
        add_overviews(quantized)

        print(f"[{name}] Writing COG → {out_path}")
        # Use gdal_translate for a proper COG layout (copy_src_overviews)
        import subprocess, shutil
        gdal_translate = shutil.which("gdal_translate")
        if gdal_translate:
            subprocess.run(
                [
                    gdal_translate,
                    "-of", "GTiff",
                    "-co", "TILED=YES",
                    "-co", f"BLOCKXSIZE={TILE_SIZE}",
                    "-co", f"BLOCKYSIZE={TILE_SIZE}",
                    "-co", "COMPRESS=DEFLATE",
                    "-co", "PREDICTOR=2",
                    "-co", "ZLEVEL=9",
                    "-co", "COPY_SRC_OVERVIEWS=YES",
                    str(quantized),
                    str(out_path),
                ],
                check=True,
            )
        else:
            # Pure rasterio fallback
            import shutil as _sh
            _sh.copy2(quantized, out_path)

    size_mb = out_path.stat().st_size / 1e6
    print(f"[{name}] Done — {out_path} ({size_mb:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build COGs for deck.gl-raster.")
    parser.add_argument(
        "--only",
        choices=list(TARGETS),
        help="Build only this target (default: both)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    args = parser.parse_args()

    targets = [args.only] if args.only else list(TARGETS)
    for name in targets:
        build(name, overwrite=args.overwrite)


if __name__ == "__main__":
    main()
