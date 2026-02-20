#!/usr/bin/env python3
"""
Update docs/wet_woodland_lnrs_regions.geojson with total_area_ha and region_area_ha
from data/wet_woodland_REPORT.txt (LNRS REGIONAL SUMMARY table). Run this after
regenerating the report from the mosaic hysteresis raster so the Regions tab
popup stats match the report and density layer.
"""

import json
import re
from pathlib import Path


def parse_report_lnrs_table(report_path: Path) -> dict[int, tuple[float, float, float]]:
    """Parse LNRS REGIONAL SUMMARY: map LNRS number -> (wet_ha, ref_area_ha, prop_pct)."""
    text = report_path.read_text()
    # Find the table (starts after "LNRS 46" / "LNRS 25" header line)
    out = {}
    for line in text.splitlines():
        m = re.match(r"LNRS\s+(\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d.]+)", line)
        if m:
            lnrs_num = int(m.group(1))
            wet_ha = float(m.group(2).replace(",", ""))
            ref_ha = float(m.group(3).replace(",", ""))
            prop = float(m.group(4))
            out[lnrs_num] = (wet_ha, ref_ha, prop)
    return out


def main():
    report_path = Path("data/wet_woodland_REPORT.txt")
    geojson_path = Path("docs/wet_woodland_lnrs_regions.geojson")

    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")
    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    stats = parse_report_lnrs_table(report_path)
    print(f"Parsed {len(stats)} LNRS rows from report")

    with open(geojson_path) as f:
        geojson = json.load(f)

    updated = 0
    for feat in geojson["features"]:
        props = feat.setdefault("properties", {})
        lnrs_id = props.get("LNRS_ID")
        if lnrs_id is None:
            continue
        # LNRS_ID can be '05', '46', etc.; report uses LNRS 5, LNRS 46
        n = int(str(lnrs_id).lstrip("0") or 0) if str(lnrs_id).isdigit() else None
        if n is None:
            continue
        if n not in stats:
            # Try exact string match (e.g. 46)
            n = int(lnrs_id) if str(lnrs_id).isdigit() else None
            if n not in stats:
                continue
        wet_ha, ref_ha, prop_pct = stats[n]
        props["total_area_ha"] = round(wet_ha, 2)
        props["region_area_ha"] = round(ref_ha, 2)
        updated += 1

    with open(geojson_path, "w") as f:
        json.dump(geojson, f, separators=(",", ":"))

    print(f"Updated {updated} features in {geojson_path}")


if __name__ == "__main__":
    main()
