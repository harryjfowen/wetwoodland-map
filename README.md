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
- **Potential (suitability):** `data/wet_woodland_potential.tif` — restoration suitability 0–1 for the Potential tab and tiles.
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

To show the **Potential** tab (raster of MaxEnt restoration suitability 0–1 with the same colour scale):

1. Place your GeoTIFF as `data/wet_woodland_potential.tif`.
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
