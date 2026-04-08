---
name: world-creation
description: Design and implement geolocated virtual world apps that combine open satellite/terrain data, procedural generation, real-time physics, VR/XR runtime, and interactive AI agents. Use when users ask for real-world-to-virtual environment creation, digital twins, open-world game/simulation architecture, SMDI/vector-style worldbuilding workflows, scenario simulation, or agent-driven interactions in synthetic or geolocated worlds.
---

# World Creation

## Overview
Use this skill to produce a **buildable plan** for a world-creation application, not just conceptual advice.

Default to existing products and open-source components that are available now. Mark speculative items as R&D.

## Required output contract
Always return these sections, in this order:
1. **Working stack recommendation** (one stack, not a list)
2. **Why this stack works now** (product availability + integration path)
3. **Implementation blueprint** (services, data flow, runtime)
4. **MVP milestones (week-by-week, first 6 weeks)**
5. **Failure points + fixes**
6. **If geolocation fails: synthetic fallback path**

If user asks for alternatives, add Product/OSS/Hybrid comparison **after** the single recommended stack.

When creating milestone plans, use `references/mvp-build-plan.md` as the default schedule template.

## Fast-path “it must work” baseline
Use this baseline unless user constraints force another choice:
- **Engine/runtime:** Unreal Engine + Cesium for Unreal
- **Data inputs:** OpenStreetMap + Copernicus/SRTM DEM + Sentinel-2 textures
- **Physics:** Unreal Chaos + simplified weather vectors
- **Agents:** behavior-tree NPCs first, optional LLM coordinator second
- **VR:** OpenXR target in Unreal

Use this baseline because each part has mature tooling and active ecosystems.

## Workflow

### 1) Define build target
Lock these values before architecture:
- Platform: PC, cloud streaming, or standalone headset
- World size: small zone, city, or regional tile set
- Fidelity: realistic, semi-stylized, stylized
- Agent scale: count of concurrent active agents
- Sim goals: training, gameplay, planning, or replay analysis

### 2) Choose bootstrap mode
Select exactly one primary mode:
- **Geolocated:** start from coordinates/place name
- **Synthetic:** start from world seed and biome rules
- **Hybrid:** geolocated core + procedural expansion

If geolocation reliability is unknown, automatically design hybrid mode.

### 3) Build ingestion pipeline
Use `references/data-sources.md` and produce concrete artifacts:
- Heightfield tiles (DEM)
- Landcover/imagery textures
- Vector layers (roads/water/buildings/POI)
- Normalized CRS transform metadata
- Version manifest (dataset name + timestamp + license)

### 4) Build world generation pipeline
Transform data in this order:
1. DEM -> terrain mesh/voxel terrain
2. Vectors -> splines, nav graph, collision meshes
3. Semantics -> biome, spawn zones, mission/event zones
4. Runtime chunks -> LOD + streaming grid

For vector workflow requests, treat vector graph as authoritative for traversal and zone logic.

### 5) Add simulation and physics
Scope realistic physics into runtime-safe layers:
- Core runtime: rigid bodies, gravity, collision, character controller
- Secondary simulation: wind, water approximation, traffic/crowd rules
- Offline/batch: heavy Monte Carlo or planner simulations

Never promise full real-world physics at runtime without explicit compute budget.

### 6) Add agents
Deploy agents in progressive complexity:
1. Deterministic NPCs (BT/GOAP)
2. Multi-agent coordination layer
3. Optional LLM planner with bounded tool actions

Require:
- Action whitelists
- Rate limits
- Replay logs and deterministic seeds

### 7) Add scenario runner + VR interactions
Include:
- Scenario schema (initial state, goals, win/fail)
- Batch runner for repeatable simulation trials
- Telemetry store (events, positions, failures)
- VR interaction map (locomotion, object interaction, UI panels)

## Product and OSS decision rule
Use `references/stack-options.md` to evaluate alternatives.

Decision priority:
1. Can team ship MVP in 6 weeks?
2. Can data pipeline be replayed deterministically?
3. Can runtime hit frame-time target on hardware?
4. Can agents be debugged safely?

Pick one stack and explain trade-offs against the next-best option.

## Troubleshooting mode (use when user says “it doesn’t work”)
Return a triage table with:
- Symptom
- Probable root cause
- Quick verification step
- Fix now
- Hardening fix later

Prioritize these failure classes:
1. CRS mismatch / wrong coordinate transforms
2. Missing or stale DEM/imagery tiles
3. Unreal/Cesium plugin version mismatch
4. Navmesh not rebuilt after terrain updates
5. Agent policy loop causing invalid actions
6. VR interaction bindings not mapped to OpenXR profile

## Quality gates before final answer
Confirm all are true:
- Includes a geolocation and a no-geolocation execution path.
- Uses publicly available data with license notes.
- Names currently available products/components.
- Distinguishes real-time vs offline simulation workloads.
- Defines a debugging plan for agents and physics.
