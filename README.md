# Wet Woodland 3D Hexagon Visualization

Interactive 3D visualization of wet woodland distribution across England using deck.gl and Mapbox.

🌐 **Live Demo:** https://harryjfowen.github.io/wetwoodland-map/

## Overview

This project visualizes wet woodland predictions as 3D hexagons where:
- **Height** represents the number of wet woodland pixels within each hexagon
- **Color** shows density with a green gradient (darker = lower, brighter = higher)
- **Interactive** controls allow rotation, zoom, and pan

## Data

- **Source Raster:** `data/wet_woodland_predictions.tif` (415 MB, stored with Git LFS)
- **Format:** Binary predictions (0 = not wet woodland, 1 = wet woodland, 255 = nodata)
- **Resolution:** 5m pixels
- **Coverage:** England
- **CRS:** OSGB36 / British National Grid (EPSG:27700)

## Setup

### Prerequisites

```bash
pip install h3 numpy rasterio tqdm
```

### Generate Hexagon Data

Run the conversion script to aggregate raster data into hexagons:

```bash
python raster_to_hexagons.py \
  --raster data/wet_woodland_predictions.tif \
  --output docs/wet_woodland_hexagons.geojson \
  --resolution 8
```

**H3 Resolution Options:**
- `7` = ~5km hexagon edge (fewer, larger hexagons - faster)
- `8` = ~1.2km hexagon edge (balanced - **recommended**)
- `9` = ~500m hexagon edge (more detail, larger file)

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
│   └── wet_woodland_predictions.tif  # Source raster (Git LFS)
├── docs/                              # GitHub Pages folder
│   ├── index.html                     # Main visualization
│   └── wet_woodland_hexagons.geojson  # Hexagon data
├── raster_to_hexagons.py             # Data conversion script
└── README.md
```

## Features

- 🗺️ Mapbox dark base layer for contrast
- 📦 3D hexagonal binning for spatial aggregation
- 🎨 Dynamic color gradient based on density
- 🖱️ Interactive controls:
  - Drag to rotate view
  - Scroll to zoom
  - Right-click drag to pan
  - Hover for hexagon details

## Technology Stack

- [deck.gl](https://deck.gl/) - WebGL-powered visualization
- [Mapbox GL JS](https://www.mapbox.com/mapbox-gljs) - Base map tiles
- [H3](https://h3geo.org/) - Hexagonal spatial indexing
- [GDAL/Rasterio](https://rasterio.readthedocs.io/) - Geospatial data processing

## License

Data and visualization by Harry J F Owen.
