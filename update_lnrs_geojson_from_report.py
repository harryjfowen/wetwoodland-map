#!/usr/bin/env python3
"""
Update LNRS GeoJSON with report-derived stats:
- Extent stats per LNRS from data/wet_woodland_REPORT.txt (LNRS REGIONAL SUMMARY)
- Suitability stats per LNRS from data/potential_stat_report.txt ([lnrs:*] blocks)

Run this after refreshing report files so the Regions tab popup aligns with
the latest extent/suitability pipeline outputs.
"""

import json
import re
from pathlib import Path
from typing import Any


def parse_extent_report(report_path: Path) -> dict[int, tuple[float, float, float]]:
    """Map LNRS number -> (wet_ha, ref_area_ha, prop_pct) from wet_woodland_REPORT."""
    text = report_path.read_text()
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


def _to_number(value: str) -> float | None:
    v = value.strip().replace(",", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def parse_potential_report(report_path: Path) -> tuple[dict[str, dict[str, Any]], float | None]:
    """
    Parse potential_stat_report [lnrs:*] sections.
    Returns:
      - map normalized LNRS name -> stats dict
      - suitability threshold (if present in [lnrs_summary])
    """
    text = report_path.read_text()
    sections: dict[str, dict[str, str]] = {}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        sec = re.match(r"^\[([^\]]+)\]$", line)
        if sec:
            current = sec.group(1)
            sections.setdefault(current, {})
            continue
        if current is None:
            continue
        kv = re.match(r"^([A-Za-z0-9_ ()\.\->=]+):\s*(.+)$", line)
        if not kv:
            continue
        key = kv.group(1).strip()
        value = kv.group(2).strip()
        sections[current][key] = value

    threshold = None
    summary = sections.get("lnrs_summary", {})
    if "suitable_threshold" in summary:
        threshold = _to_number(summary["suitable_threshold"])

    by_name: dict[str, dict[str, Any]] = {}
    for section_name, data in sections.items():
        if not section_name.startswith("lnrs:"):
            continue
        raw_name = data.get("name", section_name.split(":", 1)[1].replace("_", " "))
        key_name = _normalize_name(raw_name)
        by_name[key_name] = {
            "suitable_area_ha": _to_number(data.get("suitable_area_ha", "")),
            "suitable_pct_of_valid": _to_number(data.get("suitable_pct_of_valid", "")),
            "suitable_on_peat_area_ha": _to_number(data.get("suitable_on_peat_area_ha", "")),
            "suitable_off_peat_area_ha": _to_number(data.get("suitable_off_peat_area_ha", "")),
            "suitable_under_forest_area_ha": _to_number(data.get("suitable_under_forest_area_ha", "")),
            "suitable_bare_land_area_ha": _to_number(data.get("suitable_bare_land_area_ha", "")),
            "mean_suitability": _to_number(data.get("mean", "")),
            "median_suitability": _to_number(data.get("median", "")),
            "valid_suitability_area_ha": _to_number(data.get("valid_suitability_area_ha", "")),
            "within_100m_pct_of_valid": _to_number(data.get("within_100m_pct_of_valid", "")),
        }
    return by_name, threshold


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update LNRS GeoJSON with extent + suitability stats from report files")
    parser.add_argument("--geojson", default="docs/wet_woodland_lnrs_regions.geojson", help="Input/output LNRS GeoJSON")
    parser.add_argument("--extent-report", default="data/wet_woodland_REPORT.txt", help="Extent report with LNRS table")
    parser.add_argument(
        "--potential-report",
        default="data/potential_stat_report.txt",
        help="Suitability report with [lnrs:*] sections (optional)",
    )
    args = parser.parse_args()

    geojson_path = Path(args.geojson)
    extent_report_path = Path(args.extent_report)
    potential_report_path = Path(args.potential_report)

    if not extent_report_path.exists():
        raise FileNotFoundError(f"Extent report not found: {extent_report_path}")
    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    extent_stats = parse_extent_report(extent_report_path)
    print(f"Parsed {len(extent_stats)} LNRS extent rows from {extent_report_path}")

    potential_stats: dict[str, dict[str, Any]] = {}
    suitability_threshold = None
    if potential_report_path.exists():
        potential_stats, suitability_threshold = parse_potential_report(potential_report_path)
        print(f"Parsed {len(potential_stats)} LNRS suitability rows from {potential_report_path}")
    else:
        print(f"Potential report not found (skipping suitability updates): {potential_report_path}")

    try:
        with open(geojson_path) as f:
            geojson = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid GeoJSON JSON in {geojson_path}: {exc}. Re-export LNRS polygons (e.g. ogr2ogr) and retry."
        ) from exc

    extent_updated = 0
    suitability_updated = 0
    for feat in geojson["features"]:
        props = feat.setdefault("properties", {})
        lnrs_id = props.get("LNRS_ID", "")

        # Extent mapping by LNRS number
        n = int(str(lnrs_id).lstrip("0") or 0) if str(lnrs_id).isdigit() else None
        if n is not None and n in extent_stats:
            wet_ha, ref_ha, prop_pct = extent_stats[n]
            props["total_area_ha"] = round(wet_ha, 2)
            props["region_area_ha"] = round(ref_ha, 2)
            props["wet_prop_pct"] = round(prop_pct, 4)
            extent_updated += 1

        # Suitability mapping by LNRS name
        name = props.get("Name")
        if isinstance(name, str):
            key_name = _normalize_name(name)
            suit = potential_stats.get(key_name)
            if suit:
                for k, v in suit.items():
                    if v is not None:
                        props[k] = round(v, 3) if isinstance(v, float) else v
                if suitability_threshold is not None:
                    props["suitable_threshold"] = round(suitability_threshold, 6)
                suitability_updated += 1

    with open(geojson_path, "w") as f:
        json.dump(geojson, f, separators=(",", ":"))

    print(f"Updated {extent_updated} features with extent stats")
    print(f"Updated {suitability_updated} features with suitability stats")
    print(f"Wrote {geojson_path}")


if __name__ == "__main__":
    main()
