# Open Data Sources for Real-World Worldbuilding

## Terrain and elevation
- SRTM (near-global DEM, moderate resolution)
- Copernicus DEM (global coverage with improved regional detail)
- USGS 3DEP (high-quality US elevation where available)

## Satellite/imagery
- Copernicus Sentinel-2 (multispectral imagery)
- Landsat (long historical archive)
- NAIP (US aerial imagery for selected regions)

## Vector map layers
- OpenStreetMap (roads, buildings, POIs)
- Natural Earth (small-scale global vector layers)
- Local/state/city open GIS portals (parcel, zoning, utilities where public)

## Land cover and environmental layers
- ESA WorldCover / Copernicus land cover products
- NOAA/NASA climate or weather archives for scenario initialization

## Practical ingestion notes
- Normalize all sources into one CRS before meshing.
- Maintain a metadata table with source name, date, license, and confidence.
- Version dataset snapshots for deterministic simulation replay.
- When data is missing, fill by procedural biome synthesis and mark synthetic regions explicitly.
