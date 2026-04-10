# 6-Week MVP Build Plan (World Creation)

## Week 1: Data + coordinate foundations
- Ingest one pilot area (10km x 10km)
- Normalize all data to one CRS
- Export terrain + vector manifests

## Week 2: Terrain + vector runtime
- Load DEM terrain into engine
- Overlay roads/water/buildings from vector layers
- Validate alignment and scale

## Week 3: Physics + traversal
- Enable collision, gravity, and movement controller
- Build navmesh on generated terrain
- Add one basic dynamic system (wind or water proxy)

## Week 4: Agents + logging
- Deploy 2 deterministic agent archetypes
- Add action constraints and safety checks
- Persist simulation events for replay

## Week 5: Scenario runner
- Add scenario JSON schema
- Implement batch run + pass/fail assertions
- Surface run summaries on debug dashboard

## Week 6: VR integration + hardening
- Add OpenXR bindings and locomotion interactions
- Test frame-time budget and optimize LOD/streaming
- Run regression scenario suite and freeze MVP
