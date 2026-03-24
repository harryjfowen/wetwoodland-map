#!/usr/bin/env python3
"""
Update LNRS GeoJSON with report-derived stats:
- Extent stats from an extent report (default: data/wetwoodland_stats.txt)
  Supports either:
  - data/wet_woodland_REPORT.txt (full LNRS numeric table)
  - data/wetwoodland_stats.txt (full LNRS numeric table in the current pipeline)
- Suitability stats per LNRS from data/maxent.report.txt ([lnrs:*] blocks)

Run this after refreshing report files so the Regions tab popup aligns with
the latest extent/suitability pipeline outputs.
"""

import json
import re
from pathlib import Path
from typing import Any


def parse_extent_report(report_path: Path) -> tuple[dict[int, tuple[float, float, float]], dict[str, float]]:
    """
    Parse extent report in either format:
    - Numeric LNRS table: map LNRS_ID(int) -> (wet_ha, ref_area_ha, prop_pct)
    - Named top-20 list: map normalized LNRS name -> wet_ha
    """
    text = report_path.read_text()
    out_by_id: dict[int, tuple[float, float, float]] = {}
    out_by_name: dict[str, float] = {}

    # Full numeric table format (wet_woodland_REPORT.txt)
    for line in text.splitlines():
        m = re.match(r"LNRS\s+(\d+)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d.]+)", line)
        if m:
            lnrs_num = int(m.group(1))
            wet_ha = float(m.group(2).replace(",", ""))
            ref_ha = float(m.group(3).replace(",", ""))
            prop = float(m.group(4))
            out_by_id[lnrs_num] = (wet_ha, ref_ha, prop)

    # Named top-20 format (wetwoodland_stats.txt)
    # Example: "  Devon  16,841.9    25,088"
    for line in text.splitlines():
        m = re.match(r"\s{2,}(.+?)\s+([\d,]+\.?\d*)\s+([\d,]+)\s*$", line)
        if not m:
            continue
        name = m.group(1).strip()
        wet_ha = _to_number(m.group(2))
        if name and wet_ha is not None:
            out_by_name[_normalize_name(name)] = wet_ha

    return out_by_id, out_by_name


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
    parser.add_argument(
        "--extent-report",
        default="data/wetwoodland_stats.txt",
        help="Extent report path (optional). Supports wetwoodland_stats.txt and wet_woodland_REPORT.txt",
    )
    parser.add_argument(
        "--potential-report",
        default="data/maxent.report.txt",
        help="Suitability report with [lnrs:*] sections (optional)",
    )
    args = parser.parse_args()

    geojson_path = Path(args.geojson)
    extent_report_path = Path(args.extent_report)
    potential_report_path = Path(args.potential_report)

    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    extent_stats_by_id: dict[int, tuple[float, float, float]] = {}
    extent_stats_by_name: dict[str, float] = {}
    if extent_report_path.exists():
        extent_stats_by_id, extent_stats_by_name = parse_extent_report(extent_report_path)
        print(
            f"Parsed extent rows from {extent_report_path}: "
            f"{len(extent_stats_by_id)} by LNRS ID, {len(extent_stats_by_name)} by name"
        )
    else:
        print(f"Extent report not found (skipping extent updates): {extent_report_path}")

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
    extent_name_only_updated = 0
    suitability_updated = 0
    for feat in geojson["features"]:
        props = feat.setdefault("properties", {})
        lnrs_id = props.get("LNRS_ID", "")

        # Extent mapping by LNRS number
        n = int(str(lnrs_id).lstrip("0") or 0) if str(lnrs_id).isdigit() else None
        if n is not None and n in extent_stats_by_id:
            wet_ha, ref_ha, prop_pct = extent_stats_by_id[n]
            props["total_area_ha"] = round(wet_ha, 2)
            props["region_area_ha"] = round(ref_ha, 2)
            props["wet_prop_pct"] = round(prop_pct, 4)
            extent_updated += 1
        else:
            # Fallback: name-only extent (e.g. wetwoodland_stats top-20)
            name = props.get("Name")
            if isinstance(name, str):
                key_name = _normalize_name(name)
                wet_ha = extent_stats_by_name.get(key_name)
                if wet_ha is not None:
                    props["total_area_ha"] = round(wet_ha, 2)
                    extent_name_only_updated += 1

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

    print(f"Updated {extent_updated} features with full extent stats (id + area + proportion)")
    print(f"Updated {extent_name_only_updated} features with name-only extent area")
    print(f"Updated {suitability_updated} features with suitability stats")
    print(f"Wrote {geojson_path}")


if __name__ == "__main__":
    main()
