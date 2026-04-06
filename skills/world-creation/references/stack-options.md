# World Creation Stack Options

## 1) Product-first options available today

### Cesium ecosystem
- Cesium ion + Cesium for Unreal / Cesium for Unity
- Strength: global-scale geospatial streaming, 3D Tiles ecosystem
- Best for: geolocated digital twins and large terrain

### NVIDIA Omniverse stack
- Omniverse + OpenUSD + Isaac Sim (for robotics/simulation-heavy workflows)
- Strength: simulation workflows, USD interoperability, RTX visualization
- Best for: enterprise simulation and multi-tool pipelines

### Esri ArcGIS Maps SDKs (Unity/Unreal)
- Strength: GIS-native workflows, authoritative enterprise geodata integration
- Best for: orgs already invested in ArcGIS infrastructure

## 2) Open-source composable options

### Engine/runtime
- Godot (open-source, flexible for custom gameplay + simulation)
- Unreal Engine (source available, advanced rendering/physics)
- Unity (widely used tooling; check current license terms per use case)

### Geospatial + processing
- GDAL/rasterio (raster transforms)
- pyproj/proj (coordinate transforms)
- OSM tooling (Overpass, osm2pgsql, tile pipelines)
- 3D Tiles tooling and OpenUSD toolchains

### Physics/simulation
- Bullet/PhysX/in-engine physics
- Custom domain solvers for weather/hydrology/traffic when needed

### Agent frameworks
- Behavior trees + navmesh for deterministic NPCs
- LLM-agent orchestration for high-level planning (bounded by rule-based action layer)

## 3) Hybrid recommendation template
- Bootstrap geospatial world with Cesium or ArcGIS SDK.
- Export/bridge assets into Unreal or Unity for gameplay polish.
- Keep simulation services separate (Python/C++ microservices) for scenario batch runs.
- Use OpenUSD or glTF contracts for asset interchange.
