# Wet Woodland 3D Hexagon Visualization

Interactive 3D visualization of wet woodland distribution across England using deck.gl and MapLibre.

🌐 **Live Demo:** https://harryjfowen.github.io/wetwoodland-map/

## Overview

This project visualizes wet woodland as 3D hexagons where:
- **Height** represents the number of wet woodland pixels within each hexagon
- **Color** shows density with a green gradient (darker = lower, brighter = higher)
- **Interactive** controls allow rotation, zoom, and pan

## Data

- **Density (hexagons):** `data/wet_woodland_mosaic_hysteresis.tif` — mosaic with hysteresis; unconnected filtering etc. is already applied in the raster; the script only derives hexbins.
- **Potential (suitability):** `data/wet_woodland_potential.tif` (100m) for the Potential tab and tiles (visual). Use `data/wet_woodland_potential_10m.tif` only for **LNRS suitability-by-grade stats** (finer resolution).
- **CRS:** OSGB36 / British National Grid (EPSG:27700)

## Setup

### Prerequisites

```bash
pip install h3 numpy rasterio tqdm
```

### Generate Hexagon Data

Run the conversion script to derive hexbins from the wet woodland mosaic (filtering already in the raster):

```bash
python raster_to_hexagons.py \
  --raster data/wet_woodland_mosaic_hysteresis.tif \
  --output docs/wet_woodland_hexagons.geojson \
  --resolution 8
```

**H3 Resolution Options:**
- `7` = ~5km hexagon edge (fewer, larger hexagons - faster)
- `8` = ~1.2km hexagon edge (balanced - **recommended**)
- `9` = ~500m hexagon edge (more detail, larger file)

### Potential layer (restoration suitability 0–1)

**Heatmap rendering** uses only the **100m** TIF (or points sampled from it). **Suitability stats** in the LNRS popup use **10m** when you run the stats pipeline below.

To show the **Potential** tab (raster of MaxEnt restoration suitability 0–1 with the same colour scale):

1. Place your GeoTIFF as `data/wet_woodland_potential.tif` (100m) for the map. For **LNRS stats** (suitability-by-grade), also add `data/wet_woodland_potential_10m.tif` and run the stats pipeline below.
2. Install Pillow: `pip install Pillow`
3. Run:

```bash
python raster_potential_to_png.py --raster data/wet_woodland_potential.tif
```

This writes `docs/potential.png` and `docs/potential_bounds.json`. Commit and push so the Potential tab works on the live site.

For a **raster tile layer** (higher resolution as you zoom in), generate tiles with GDAL:

```bash
pip install rasterio Pillow   # if not already
python raster_potential_to_tiles.py --raster data/wet_woodland_potential.tif
```

This writes `docs/potential_tiles/{z}/{x}/{y}.png`. Requires `gdal2tiles.py` (from GDAL). Optionally use `--max-zoom 10` to limit zoom levels.

### LNRS suitability stats (10m)

The **map** uses the 100m suitability raster for the Potential tab. The **LNRS region popup** “Suitability for restoration” (ha by land grade) is computed from a **10m** points file for finer stats. To generate it:

1. Place the 10m suitability raster as `data/wet_woodland_potential_10m.tif`.
2. Rasterize land value to the 10m grid and sample 10m points with land class:

```bash
python landvalue_to_raster.py --potential-raster data/wet_woodland_potential_10m.tif --output data/landvalue_classes_10m.tif
python raster_potential_to_points.py --raster data/wet_woodland_potential_10m.tif --landvalue data/landvalue_classes_10m.tif --output docs/potential_points_stats.bin --binary
```

3. Update LNRS regions with suitability-by-grade (script uses `potential_points_stats.bin` when present):

```bash
python lnrs_suitability_stats.py
```

### Refreshing LNRS region data (patch distribution, peat, etc.)

The LNRS stats in the Regions tab (patch distribution, on/off peat, effective mesh size, etc.) come from **`data/wet_woodland_lnrs_regions.gpkg`**, which is produced by your external pipeline (not this repo). After you refresh that GPKG:

1. Export to GeoJSON for the web app:
   ```bash
   ogr2ogr -f GeoJSON docs/wet_woodland_lnrs_regions.geojson data/wet_woodland_lnrs_regions.gpkg
   ```
2. Update LNRS per-region extent and suitability totals from report files:
   ```bash
   python update_lnrs_geojson_from_report.py
   ```
   This pulls:
   - Extent from `data/wetwoodland_stats.txt` by default (or `--extent-report`), updating `total_area_ha`
   - Suitability totals from `data/potential_stat_report.txt` (`suitable_area_ha`, peat/forest splits, etc.)
3. Optionally refresh suitability-by-grade fields (`suitable_ha_grade_12/3/45`) using the 10m points workflow above.

## Local Testing

Test the visualization locally:

```bash
cd docs
python3 -m http.server 8000
```

Open http://localhost:8000 in your browser.

## GitHub Pages Deployment

The visualization is automatically hosted via GitHub Pages from the `/docs` folder.

Any changes to `docs/index.html` or `docs/*.geojson` will be reflected on the live site after pushing to GitHub.

## Project Structure

```
wetwoodland-map/
├── data/
│   ├── wet_woodland_predictions.tif  # Source raster (Git LFS)
│   └── wet_woodland_potential.tif     # Optional: 0–1 suitability for Potential tab
├── docs/                              # GitHub Pages folder
│   ├── index.html                     # Main visualization
│   ├── wet_woodland_hexagons.geojson  # Hexagon data
│   ├── potential.png                  # Optional: from raster_potential_to_png.py
│   ├── potential_bounds.json         # Optional: bounds for BitmapLayer fallback
│   └── potential_tiles/               # Optional: {z}/{x}/{y}.png from raster_potential_to_tiles.py
├── raster_to_hexagons.py             # Hexagon conversion script
├── raster_potential_to_png.py        # Potential raster → PNG + bounds
├── raster_potential_to_tiles.py      # Potential raster → tile pyramid (zoom‑dependent resolution)
└── README.md
```

## Features

- **Three views:** **Density** (3D hexagons), **LNRS Regions** (polygons with stats), **Potential** (raster of restoration suitability 0–1, same colour scale)
- 🗺️ CartoDB Dark Matter base layer (via MapLibre - no API key required!)
- 📦 3D hexagonal binning for spatial aggregation
- 🎨 Shared 6-color gradient (cyan → turquoise → yellow → orange → red)
- ⚙️ Interactive controls:
  - Height exaggeration slider (1x to 10x)
  - Opacity slider (0.5 to 1.0)
  - Drag to rotate view
  - Scroll to zoom
  - Right-click drag to pan
  - Hover for hexagon details
- 💡 Professional lighting and material effects

## Technology Stack

- [deck.gl](https://deck.gl/) - WebGL-powered visualization
- [MapLibre GL](https://maplibre.org/) - Open-source base maps (no API token needed)
- [CartoDB](https://carto.com/basemaps/) - Free dark matter base map style
- [H3](https://h3geo.org/) - Hexagonal spatial indexing
- [GDAL/Rasterio](https://rasterio.readthedocs.io/) - Geospatial data processing

## License

Data and visualization by Harry J F Owen.
