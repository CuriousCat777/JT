# World Creation Stack Options

## Recommended baseline (most likely to work quickly)
- Unreal Engine + Cesium for Unreal + OpenXR
- OSM for vectors + Copernicus/SRTM for terrain + Sentinel-2 for textures
- Behavior-tree agents first; optional LLM planner as a bounded layer

## Product-first options available today

### Cesium ecosystem
- Cesium ion + Cesium for Unreal / Cesium for Unity
- Strength: global-scale geospatial streaming, 3D Tiles ecosystem
- Best for: geolocated digital twins and large terrain

### NVIDIA Omniverse stack
- Omniverse + OpenUSD + Isaac Sim (simulation-heavy workflows)
- Strength: simulation workflows, USD interoperability, RTX visualization
- Best for: enterprise simulation and robotics workflows

### Esri ArcGIS Maps SDKs (Unity/Unreal)
- Strength: GIS-native workflows, enterprise geodata integration
- Best for: teams already invested in ArcGIS infrastructure

## Open-source composable options

### Engine/runtime
- Godot (open-source, flexible for custom gameplay + simulation)
- Unreal Engine (source-available, advanced rendering/physics)
- Unity (widely used tooling; verify license fit before selection)

### Geospatial + processing
- GDAL/rasterio (raster transforms)
- pyproj/proj (coordinate transforms)
- OSM tooling (Overpass, osm2pgsql, tile pipelines)
- 3D Tiles and OpenUSD tooling for interchange

### Physics/simulation
- In-engine physics (Chaos/PhysX/Bullet depending on engine)
- Domain-specific offline solvers for weather/hydrology/traffic

### Agent frameworks
- Behavior trees + navmesh for deterministic NPC behaviors
- LLM orchestration for high-level planning with bounded action layer

## Hybrid template
- Bootstrap geospatial world with Cesium or ArcGIS SDK.
- Export/bridge assets into Unreal or Unity for gameplay polish.
- Keep heavy simulation as external Python/C++ services for batch scenarios.
- Use OpenUSD or glTF contracts for asset interchange.
