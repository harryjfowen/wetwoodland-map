#!/usr/bin/env python3
"""
Build Cloud-Optimised GeoTIFFs (EPSG:3857, uint8) for the web app.

Outputs:
  docs/wetwoodland_probability.cog.bin        — band 1 of wet_woodland_potential.tif
  docs/wetwoodland_probability_1km.cog.bin    — 1 km aggregate of band 1
  docs/wetwoodland_extent_b2.cog.bin          — band 2 of wet_woodland_mosaic_hysteresis.tif
  docs/wetwoodland_extent_b2_1km.cog.bin      — 1 km aggregate of extent band 2

Usage:
  python make_cog.py                        # build all targets
  python make_cog.py --only extent          # build only fine extent band 2
  python make_cog.py --only extent_coarse   # build only coarse extent band 2
  python make_cog.py --overwrite            # force rebuild
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
        "resolution": 40,
        "resampling": Resampling.nearest,
        "compress": "DEFLATE",
        "level": 9,
    },
    "probability_coarse": {
        "src": "data/wet_woodland_potential.tif",
        "band": 1,
        "out": "docs/wetwoodland_probability_1km.cog.bin",
        "resolution": 1000,
        "resampling": Resampling.average,
        "min_valid_fraction": 0.5,
    },
    "extent": {
        "src": "data/wet_woodland_mosaic_hysteresis.tif",
        "band": 2,
        "out": "docs/wetwoodland_extent_b2.cog.bin",
        "resolution": 30,
        "resampling": Resampling.nearest,
        "compress": "DEFLATE",
        "level": 9,
        "overview_resampling": "rms",
    },
    "extent_coarse": {
        "src": "data/wet_woodland_mosaic_hysteresis.tif",
        "band": 2,
        "out": "docs/wetwoodland_extent_b2_1km.cog.bin",
        "resolution": 1000,
        "resampling": Resampling.average,
        "min_valid_fraction": 0.5,
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
    Quantize float32 0-1 → uint8 with 0 preserved for true zero probability,
    1-254 for positive values, and 255 for nodata.

    Zero-valued probability must remain 0 so the web renderer can keep those
    pixels transparent. Collapsing all valid zeros into 1 makes sparse rasters
    look washed out or effectively invisible.
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
                zero = valid & (data <= 0)
                positive = valid & (data > 0)
                out[zero] = 0
                out[positive] = np.clip(
                    np.round(data[positive] * 254.0).astype(np.int32), 1, 254
                ).astype(np.uint8)
                dst.write(out, 1, window=window)


def apply_valid_fraction_mask(
    source_path: Path,
    warped_path: Path,
    min_valid_fraction: float,
) -> None:
    """
    Drop coarse cells that are only weakly supported by valid source data.

    This prevents the low-zoom aggregate from bleeding beyond the England mask
    along the coastline, where an averaged 1 km cell may only contain a small
    sliver of valid pixels.
    """
    with rasterio.open(source_path) as src, rasterio.open(warped_path, "r+") as dst:
        src_band = src.read(1, masked=False)
        valid = np.isfinite(src_band)
        if src.nodata is not None:
            valid &= src_band != float(src.nodata)
        valid_src = valid.astype(np.uint8)

        coverage = np.zeros((dst.height, dst.width), dtype=np.float32)
        reproject(
            source=valid_src,
            destination=coverage,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst.transform,
            dst_crs=dst.crs,
            src_nodata=None,
            dst_nodata=0.0,
            resampling=Resampling.average,
        )

        data = dst.read(1)
        dst_nodata = dst.nodata
        if dst_nodata is None:
            raise ValueError("Expected warped raster to carry nodata for coverage masking.")
        data[coverage < min_valid_fraction] = dst_nodata
        dst.write(data, 1)


def add_overviews(path: Path, compress: str = "DEFLATE", resampling: str = "average") -> None:
    """Build internal overviews with proper compression."""
    import subprocess, shutil
    gdal_addo = shutil.which("gdaladdo")
    if gdal_addo:
        cmd = [
            gdal_addo, "-r", resampling,
            "--config", "GDAL_TIFF_OVR_BLOCKSIZE", str(TILE_SIZE),
            "--config", "COMPRESS_OVERVIEW", compress,
            "--config", "PREDICTOR_OVERVIEW", "2",
            "--config", "ZLEVEL_OVERVIEW", "9",
            str(path),
        ] + [str(f) for f in OVERVIEW_FACTORS]
        subprocess.run(cmd, check=True)
    else:
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

        min_valid_fraction = cfg.get("min_valid_fraction")
        if min_valid_fraction is not None:
            print(f"[{name}] Applying valid-coverage mask …")
            apply_valid_fraction_mask(src_path, warped, float(min_valid_fraction))

        print(f"[{name}] Quantizing to uint8 …")
        quantize_to_uint8(warped, quantized)

        if cfg.get("overview_zero_as_nodata"):
            print(f"[{name}] Masking zero pixels to nodata for overview averaging …")
            with rasterio.open(quantized, "r+") as ds:
                data = ds.read(1)
                data[data == 0] = NODATA_UINT8
                ds.write(data, 1)

        print(f"[{name}] Writing COG → {out_path}")
        # Use gdal_translate so individual targets can choose their COG settings.
        import subprocess, shutil
        gdal_translate = shutil.which("gdal_translate")
        if gdal_translate:
            driver = cfg.get("driver", "GTiff")
            compress = cfg.get("compress", "DEFLATE")
            translate_cmd = [
                gdal_translate,
                "-of", str(driver),
                "-co", f"BLOCKSIZE={TILE_SIZE}" if driver == "COG" else f"BLOCKXSIZE={TILE_SIZE}",
            ]
            if driver != "COG":
                print(f"[{name}] Building overviews …")
                add_overviews(quantized, resampling=cfg.get("overview_resampling", "average"))
                translate_cmd.extend(
                    [
                        "-co", "TILED=YES",
                        "-co", f"BLOCKYSIZE={TILE_SIZE}",
                        "-co", f"COMPRESS={compress}",
                        "-co", "PREDICTOR=2",
                        "-co", f"ZLEVEL={cfg.get('level', 9)}",
                        "-co", "COPY_SRC_OVERVIEWS=YES",
                    ]
                )
            else:
                overview_compress = cfg.get("overview_compress", compress)
                translate_cmd.extend(
                    [
                        "-co", f"COMPRESS={compress}",
                        "-co", f"OVERVIEW_COMPRESS={overview_compress}",
                        "-co", "RESAMPLING=NEAREST",
                        "-co", "OVERVIEW_RESAMPLING=NEAREST",
                        "-co", "NUM_THREADS=ALL_CPUS",
                    ]
                )
            translate_cmd.extend([str(quantized), str(out_path)])
            subprocess.run(translate_cmd, check=True)
        else:
            print(f"[{name}] Building overviews …")
            add_overviews(quantized)
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
