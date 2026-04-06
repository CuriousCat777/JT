---
name: world-creation
description: Design and implement geolocated virtual world pipelines that combine open satellite/terrain data, procedural generation, real-time physics, VR/XR runtime, and interactive AI agents. Use when users ask for real-world-to-virtual environment creation, digital twins, open-world game/simulation architecture, SMDI/vector-style worldbuilding workflows, scenario simulation, or agent-driven interactions in synthetic or geolocated worlds.
---

# World Creation

## Overview
Use this skill to convert a location (or a synthetic seed) into a playable/simulatable world that supports physics, VR interaction, and autonomous agents.

Prioritize open-source components, public datasets, and existing products before proposing custom R&D.

## Workflow

### 1) Clarify the target experience
Capture the intended output in one sentence:
- **Digital twin** (real place fidelity first)
- **Stylized open world** (gameplay first, Pokemon-like exploration)
- **Simulation sandbox** (scenario testing first)

Then lock constraints:
- Runtime target: desktop, web, standalone VR headset
- Scale target: neighborhood, city, region, planet chunk
- Fidelity target: photoreal, semi-real, stylized
- Multiplayer/agent count target

### 2) Select world bootstrap mode
Choose one and state why:
- **Geolocated mode:** Start from coordinates, geocoder, or place name.
- **Synthetic mode:** Start from seed + biome presets when no geolocation is available.
- **Hybrid mode:** Start geolocated, then fill missing areas procedurally.

If user says geolocation is optional, implement both with the same downstream pipeline.

### 3) Build the data ingestion layer
Use `references/data-sources.md` to select terrain, imagery, buildings, roads, and climate inputs.

Minimum ingestion outputs:
- DEM/heightfield tiles
- Land cover or texture classes
- Vector layers (roads, water, buildings, POI)
- CRS/projection normalization to engine coordinates

### 4) Choose engine stack using product-first rule
Use `references/stack-options.md`.

Always present:
- **Existing product path** (fastest to value)
- **Open-source composable path** (maximum control)
- **Hybrid path** (product for bootstrap + OSS for extension)

### 5) Generate world representation
Implement this ordered transform:
1. Tiles/rasters -> terrain mesh/voxel terrain
2. Vectors -> splines, nav graph, collision geometry
3. Semantic layers -> biome rules, spawn zones, mission nodes
4. LOD + streaming -> chunked runtime loading

For “vector workflow” requests, emphasize vector-first map layers (roads/paths/parcels) and derive traversal + gameplay graph from them.

### 6) Add simulation + physics
Define simulation domains explicitly:
- Rigid-body and character physics
- Fluids/weather approximations
- Traffic/crowd or ecosystem rules
- Time-of-day and seasonal loops

If user asks “real world physics,” specify model fidelity and where approximations are acceptable.

### 7) Add agents
Design agents in three layers:
- **Perception:** local map, events, nearby entities
- **Planning:** goals, behavior trees/GOAP/LLM orchestration
- **Action:** movement, interaction, tool use, dialogue

Require guardrails:
- Bounded action space
- Rate limits and safe tool permissions
- Deterministic replay mode for debugging simulations

### 8) Deploy to VR + scenario runner
Include:
- VR locomotion/interactions
- Scenario authoring (initial conditions + success criteria)
- Batch simulation runner + telemetry logs
- Optional human-in-the-loop override panel

## Output format
When asked to “make” or “design” a world creation app, return these sections:
1. **Architecture diagram (text form)**
2. **Tech stack options (Product / OSS / Hybrid)**
3. **Data sources with licenses**
4. **MVP scope in 2-4 milestones**
5. **Risk list + mitigations**
6. **Next implementation step (first 1-2 weeks)**

## Quality checklist
Before finalizing, verify:
- A no-geolocation fallback exists.
- Public/open data sources are identified with update cadence.
- Physics scope matches runtime constraints.
- Agent behavior is observable and replayable.
- Proposed components are available today (or clearly marked R&D).
