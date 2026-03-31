# Wet Woodland Visualization

Interactive 3D visualization of wet woodland distribution across England.

Live demo: https://harryjfowen.github.io/wetwoodland-map/

## Tech Stack

- **deck.gl** - WebGL 3D visualization layer
- **MapLibre GL** - Open-source basemap (CartoDB Dark Matter)
- **Cloudflare R2** - Cloud-Optimized GeoTIFF (COG) raster hosting
- **H3** - Hexagonal spatial indexing
- **GeoJSON** - Vector tile data (hexagons, LNRS regions, points)

## Four Views

- **Extent Map** - 10m probability raster via Cloud-Optimized GeoTIFF hosted on Cloudflare R2
- **Density** - 3D H3 hexagons colored by wet woodland pixel count
- **LNRS Regions** - Polygon statistics: extent, peat distribution, suitability by land grade
- **Restoration Potential** - Sampled suitability points (0–1 scale), color-coded by land grade

## Data Pipeline

Source data is processed into web-ready formats using Python scripts in `pipeline/`:

- `raster_to_hexagons.py` - Convert raster to H3 hexagon GeoJSON
- `raster_potential_to_points.py` - Sample suitability raster to point features
- `raster_potential_to_tiles.py` - Generate tile pyramid for zoom-dependent raster rendering
- `make_cog.py` - Build Cloud-Optimized GeoTIFF for R2 hosting
- `lnrs_suitability_stats.py` - Compute suitability by land grade per LNRS region
- `update_lnrs_geojson_from_report.py` - Refresh LNRS region totals from report files
- `extract_summary_from_report.py` - Parse extent and suitability statistics
- `landvalue_to_raster.py` - Rasterize land value polygons to match suitability grid

## Local Development

```bash
cd docs
python3 -m http.server 8000
```

Visit http://localhost:8000

## Deployment

The app is hosted on GitHub Pages from the `/docs` folder. The COG raster is served from Cloudflare R2.

## Data

- **Required in docs/:**
  - `wet_woodland_hexagons.geojson` - Density layer
  - `wet_woodland_lnrs_regions.geojson` - LNRS regions layer
  - `potential_points.bin` or `potential_points.json` - Potential layer
  - `wetwoodland_extent_b2.cog.bin` - Local dev copy of raster (primary served from R2)

- **Required in data/:**
  - `wet_woodland_potential.tif` - Suitability raster (100m, 0–1)
  - `wet_woodland_lnrs_regions.gpkg` - LNRS region boundaries
  - `landvalue_classes.tif` - Land value classification raster

## Project Structure

```
pipeline/              # Data processing scripts
data/                  # Source rasters and geodata
docs/                  # Web app (GitHub Pages)
  ├── index.html       # Main visualization
  ├── wet_woodland_hexagons.geojson
  ├── wet_woodland_lnrs_regions.geojson
  ├── potential_points.bin / .json
  └── wetwoodland_extent_b2.cog.bin
```
