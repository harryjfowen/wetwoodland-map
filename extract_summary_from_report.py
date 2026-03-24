#!/usr/bin/env python3
"""
Extract national wet woodland summary stats from wetwoodland_stats.txt into JSON
for the static web app.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def parse_report(report_path: Path) -> dict:
    text = report_path.read_text()

    def grab(pattern: str) -> re.Match[str]:
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            raise ValueError(f"Missing pattern: {pattern}")
        return match

    total = grab(r"Total Wet Woodland:\s+([\d,]+\.?\d*) ha \(([\d,]+\.?\d*) km²\)")
    forest_pct = grab(r"Wet woodland as % of forest:\s+([\d.]+)%")
    on_peat = grab(r"On Peat:\s+([\d,]+\.?\d*) ha \(([\d.]+)%\)")
    off_peat = grab(r"Off Peat:\s+([\d,]+\.?\d*) ha \(([\d.]+)%\)")

    total_patches = grab(r"Total Number of Patches:\s+([\d,]+)")
    mean_patch = grab(r"Mean Patch Size:\s+([\d,]+\.?\d*) ha")
    median_patch = grab(r"Median Patch Size:\s+([\d,]+\.?\d*) ha")

    patch_rows = []
    for label in ["≤ 0.01 ha", "0.01-0.1 ha", "0.1-1 ha", "1-5 ha", "5-10 ha", "≥ 10 ha"]:
        row = grab(
            rf"{re.escape(label)}:\s+([\d,]+\.?\d*) ha \(([\d.]+)%\)\s+—\s+([\d,]+) patches"
        )
        patch_rows.append(
            {
                "label": label,
                "area_ha": _num(row.group(1)),
                "pct": float(row.group(2)),
                "patches": int(row.group(3).replace(",", "")),
            }
        )

    mesh = grab(r"Effective Mesh Size:\s+([\d,]+\.?\d*) ha \(([\d,]+\.?\d*) km²\)")
    mean_nn = grab(r"Nearest Neighbor Distances:\s*\n\s+Mean:\s+([\d,]+\.?\d*) m")
    generated = grab(r"Report generated:\s+(.+)$")

    return {
        "coverage": {
            "total_area_ha": _num(total.group(1)),
            "total_area_km2": _num(total.group(2)),
            "wet_pct_of_forest": float(forest_pct.group(1)),
            "on_peat_ha": _num(on_peat.group(1)),
            "on_peat_pct": float(on_peat.group(2)),
            "off_peat_ha": _num(off_peat.group(1)),
            "off_peat_pct": float(off_peat.group(2)),
        },
        "patch_summary": {
            "total_patches": int(total_patches.group(1).replace(",", "")),
            "mean_patch_ha": _num(mean_patch.group(1)),
            "median_patch_ha": _num(median_patch.group(1)),
        },
        "patch_distribution": patch_rows,
        "fragmentation": {
            "effective_mesh_size_ha": _num(mesh.group(1)),
            "effective_mesh_size_km2": _num(mesh.group(2)),
            "mean_nn_m": _num(mean_nn.group(1)),
        },
        "report_generated": generated.group(1).strip(),
        "source_report": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract national summary stats for the web app")
    parser.add_argument("--report", default="data/wetwoodland_stats.txt", help="Input report")
    parser.add_argument("--output", default="docs/wetwoodland_summary.json", help="Output JSON")
    args = parser.parse_args()

    report_path = Path(args.report)
    output_path = Path(args.output)

    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    summary = parse_report(report_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, separators=(",", ":")))
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
