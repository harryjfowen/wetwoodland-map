#!/usr/bin/env python3
"""
Convert wet woodland raster to hexagon-aggregated GeoJSON for deck.gl visualization.
Counts wet woodland pixels within hexagonal bins.

Use wet_woodland_mosaic_hysteresis.tif when filtering (unconnected etc.) is already
done in the raster; this script only derives the hexbins.
"""

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
import json
from pathlib import Path
import h3
from tqdm import tqdm

def raster_to_hexagons(raster_path, output_geojson, h3_resolution=7, threshold=0.0):
    """
    Convert raster to hexagon-aggregated data.

    Parameters:
    - raster_path: Path to wet woodland raster (e.g. mosaic hysteresis; filtering already applied)
    - output_geojson: Output GeoJSON path
    - h3_resolution: H3 hexagon resolution (7 = ~5km edge, 8 = ~1.2km edge, 9 = ~500m edge)
    - threshold: Pixels with value > threshold count as wet woodland (default 0 = any positive)
    """

    print(f"Reading raster: {raster_path}")
    print(f"H3 resolution: {h3_resolution}, threshold: > {threshold}")

    with rasterio.open(raster_path) as src:
        # Read band 1 (e.g. mosaic hysteresis: 0/1 or 0–1, filtering already applied)
        data = src.read(1)
        transform = src.transform
        crs = src.crs
        nodata = src.nodata if src.nodata is not None else 255

        print(f"Raster size: {data.shape}")
        print(f"CRS: {crs}")
        print(f"NoData: {nodata}")

        # Get bounds in WGS84 (lat/lon) for H3
        bounds_wgs84 = transform_bounds(crs, 'EPSG:4326', *src.bounds)
        print(f"Bounds (WGS84): {bounds_wgs84}")

        # Wet woodland = valid and value > threshold (mosaic hysteresis: use >0 for binary)
        valid_mask = (data != nodata) & np.isfinite(data)
        wet_mask = valid_mask & (data > threshold)
        wet_count = wet_mask.sum()
        print(f"Total valid pixels: {valid_mask.sum():,}")
        print(f"Total wet woodland pixels (>{threshold}): {wet_count:,}")

        if wet_count == 0:
            print("No wet woodland pixels found!")
            return

        # Get pixel coordinates
        rows, cols = np.where(wet_mask)

        # Sample if too many points (for performance)
        max_points = 1_000_000
        if len(rows) > max_points:
            print(f"Sampling {max_points:,} of {len(rows):,} points...")
            indices = np.random.choice(len(rows), max_points, replace=False)
            rows = rows[indices]
            cols = cols[indices]

        print(f"Processing {len(rows):,} wet woodland pixels...")

        # Convert pixel coordinates to geographic coordinates
        hexagon_counts = {}

        for row, col in tqdm(zip(rows, cols), total=len(rows), desc="Aggregating to hexagons"):
            # Get pixel center coordinates in raster CRS
            x, y = transform * (col + 0.5, row + 0.5)

            # Transform to WGS84 (lat/lon) for H3
            from rasterio.warp import transform as rio_transform
            lon, lat = rio_transform(crs, 'EPSG:4326', [x], [y])

            # Get H3 hexagon index
            try:
                h3_index = h3.latlng_to_cell(lat[0], lon[0], h3_resolution)
                hexagon_counts[h3_index] = hexagon_counts.get(h3_index, 0) + 1
            except Exception as e:
                # Skip invalid coordinates
                continue

        print(f"Total hexagons: {len(hexagon_counts):,}")

        # Convert to GeoJSON
        features = []
        for h3_index, count in tqdm(hexagon_counts.items(), desc="Creating GeoJSON"):
            # Get hexagon boundary
            boundary = h3.cell_to_boundary(h3_index)
            # H3 returns (lat, lon), GeoJSON needs [lon, lat] - round to 5 decimal places
            coords = [[round(lon, 5), round(lat, 5)] for lat, lon in boundary]
            coords.append(coords[0])  # Close the polygon

            feature = {
                "type": "Feature",
                "properties": {
                    "count": count,
                    "h3_index": h3_index
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                }
            }
            features.append(feature)

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        # Write output
        output_path = Path(output_geojson)
        output_path.parent.mkdir(exist_ok=True, parents=True)

        with open(output_path, 'w') as f:
            json.dump(geojson, f)

        print(f"\n✅ Created {output_path}")
        print(f"   Hexagons: {len(features):,}")
        print(f"   Total wet woodland pixels: {sum(hexagon_counts.values()):,}")
        print(f"   Max count per hexagon: {max(hexagon_counts.values()):,}")
        print(f"   File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert wet woodland raster to hexagons for deck.gl. Use mosaic hysteresis when filtering is already applied."
    )
    parser.add_argument(
        "--raster",
        default="data/wet_woodland_mosaic_hysteresis.tif",
        help="Input raster (e.g. wet_woodland_mosaic_hysteresis.tif; filtering already in raster)",
    )
    parser.add_argument(
        "--output",
        default="docs/wet_woodland_hexagons.geojson",
        help="Output GeoJSON (use docs/ for the web app)",
    )
    parser.add_argument("--resolution", type=int, default=8, help="H3 resolution (7=~5km, 8=~1.2km, 9=~500m)")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.0,
        help="Count pixels with value > this as wet woodland (default 0 = any positive)",
    )

    args = parser.parse_args()

    raster_to_hexagons(args.raster, args.output, args.resolution, threshold=args.threshold)
