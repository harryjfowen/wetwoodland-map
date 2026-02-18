#!/usr/bin/env python3
"""
Add suitability-for-restoration stats to LNRS region polygons: hectares of land
suitable for restoration (potential >= 0.15) by agricultural land class
(Grade 1-2, Grade 3, Grade 4-5) per region. Uses potential_points.bin (16-byte:
lon, lat, value, class). Requires: pip install shapely.
"""

import json
import struct
from pathlib import Path

import numpy as np
from shapely import prepare
from shapely.geometry import shape, Point


def main():
    import argparse
    p = argparse.ArgumentParser(description="Add suitability ha by land class to LNRS GeoJSON")
    p.add_argument("--regions", default="docs/wet_woodland_lnrs_regions.geojson", help="LNRS GeoJSON")
    p.add_argument("--points", default="docs/potential_points.bin", help="Potential points .bin (16 bytes/point)")
    p.add_argument("--output", default=None, help="Output GeoJSON (default: overwrite --regions)")
    args = p.parse_args()
    out_path = Path(args.output) if args.output else Path(args.regions)
    regions_path = Path(args.regions)
    points_path = Path(args.points)

    if not points_path.exists():
        raise FileNotFoundError(f"Points file not found: {points_path}. Run raster_potential_to_points.py with --landvalue first.")
    if not regions_path.exists():
        raise FileNotFoundError(f"Regions file not found: {regions_path}")

    # Load points: 16 bytes each = lon, lat, value, class (float32)
    buf = points_path.read_bytes()
    n = len(buf) // 16
    arr = np.frombuffer(buf, dtype=np.float32).reshape(n, 4)
    valid = (arr[:, 3] >= 0) & (arr[:, 3] <= 2)
    lons = arr[valid, 0]
    lats = arr[valid, 1]
    classes = arr[valid, 3].astype(np.int32)
    print(f"Loaded {len(lons):,} potential points (with land class) from {points_path}")

    # Load regions
    with open(regions_path) as f:
        geojson = json.load(f)
    features = geojson["features"]
    print(f"Loaded {len(features)} LNRS regions")

    # Build prepared geometries and init counts
    shapes = []
    for i, feat in enumerate(features):
        geom = feat.get("geometry")
        if not geom:
            shapes.append(None)
            continue
        shp = shape(geom)
        prepare(shp)
        shapes.append(shp)

    # Count points per region per class: counts[feature_idx][class_012]
    counts = [[0, 0, 0] for _ in range(len(features))]
    for i, shp in enumerate(shapes):
        if shp is None:
            continue
        minx, miny, maxx, maxy = shp.bounds
        in_bbox = (lons >= minx) & (lons <= maxx) & (lats >= miny) & (lats <= maxy)
        cand = np.where(in_bbox)[0]
        for j in cand:
            if shp.contains(Point(lons[j], lats[j])):
                counts[i][classes[j]] += 1
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(features)} regions...")

    # Attach properties (each point = 1 ha)
    for i, feat in enumerate(features):
        props = feat.setdefault("properties", {})
        props["suitable_ha_grade_12"] = round(counts[i][0], 2)
        props["suitable_ha_grade_3"] = round(counts[i][1], 2)
        props["suitable_ha_grade_45"] = round(counts[i][2], 2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(geojson, f, separators=(",", ":"))
    print(f"Wrote {out_path} with suitable_ha_grade_12, suitable_ha_grade_3, suitable_ha_grade_45 per feature.")


if __name__ == "__main__":
    main()
