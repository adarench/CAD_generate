# CadQuery Technical Roadmap For An AI Land Development Design Engine

## 1. CadQuery Capability Analysis

CadQuery is a Python parametric CAD framework built on top of OpenCascade. In repository terms, the core modeling surface is centered around:

- `cadquery/cq.py`: the `Workplane` API and fluent solid-modeling chain
- `cadquery/sketch.py`: 2D sketch construction and selection/edit workflows
- `cadquery/assembly.py`: multi-part assemblies, locations, and constraint solving
- `cadquery/occ_impl/`: OpenCascade-backed shape, import, and export implementations

What CadQuery provides technically:

- Geometry primitives:
  - 2D wires, edges, circles, arcs, splines, polygons
  - 3D solids and shells from boxes, cylinders, spheres, lofts, sweeps, revolves, and extrusions
  - topological access to vertices, edges, wires, faces, shells, solids, and compounds
- Workplane model:
  - a local coordinate frame plus a stack of selected geometry
  - selection-chaining such as faces-to-workplane-to-sketch-to-extrude
  - repeatable parametric scripts driven by dimensions and higher-level inputs
- Parametric operations:
  - `extrude`, `loft`, `sweep`, `revolve`
  - booleans such as `union`, `cut`, `intersect`
  - offsets, shells, fillets, chamfers, arrays, mirrors, patterns
  - selectors that let later operations target faces, edges, or tagged features
- Sketch generation:
  - profile creation from segments, arcs, slots, polygons, and constraints
  - face building from closed profiles before downstream operations
- Assembly constraints:
  - named parts with `Location`s
  - mating-style constraints and solve steps for relative placement
- Export capabilities:
  - STEP and STL are first-class for solids
  - DXF export exists primarily for 2D sketches / projected geometry rather than rich civil drafting semantics
  - additional formats in the ecosystem depend on OpenCascade export paths and tessellation choices

What CadQuery can power in this system:

- parametric generation of parcel footprints, road corridors, lot pads, easement solids, and utility corridor solids
- thin-solid or surface representations for CAD interchange such as STEP
- section cuts and derived 2D outlines for downstream DXF export
- a deterministic geometry backend behind an AI planner, with reproducible scripts instead of manual drafting

Where CadQuery is weak for civil CAD workflows:

- no native parcel topology, survey bearings, station equations, alignments, profiles, or corridors comparable to Civil 3D
- no GIS-native ingestion stack for parcels, coordinate reference systems, or topology-clean polygon overlays
- no built-in zoning engine, setback solver, road centerline design standards, or stormwater/drainage modeling
- DXF support is geometry-oriented, not annotation-rich civil drafting with labels, styles, blocks, and paper-space conventions
- topography, grading, cut/fill, and utility network engineering require substantial external logic

Bottom line: CadQuery is a useful geometric kernel adapter for deterministic shape construction, but it is not itself a civil design platform. It should sit below a dedicated constraints, computational geometry, and rules layer.

## 2. Architecture For AI-Driven CAD Generation

```text
+----------------------+      +------------------------+      +----------------------+
| Natural Language UI  | ---> | Intent Extraction LLM | ---> | Constraint Graph     |
| CLI / API / CRM      |      | prompt -> JSON        |      | typed site model     |
+----------------------+      +------------------------+      +----------------------+
                                                                        |
                                                                        v
+----------------------+      +------------------------+      +----------------------+
| GIS / Parcel Inputs  | ---> | Spatial Normalization  | ---> | Geometry Orchestrator|
| SHP / GeoJSON / CSV  |      | CRS, cleanup, bounds   |      | algorithm selection  |
+----------------------+      +------------------------+      +----------------------+
                                                                        |
                                                                        v
+----------------------+      +------------------------+      +----------------------+
| Optimization Engine  | <--> | Constraint Solvers     | <--> | CadQuery Backend     |
| lot yield / scoring  |      | setbacks / frontage    |      | solids / wires       |
+----------------------+      +------------------------+      +----------------------+
                                                                        |
                                                                        v
+----------------------+      +------------------------+      +----------------------+
| Export Layer         | ---> | Visualization Layer    | ---> | User Review          |
| DXF STEP GeoJSON     |      | web preview / AutoCAD  |      | iterate / approve    |
+----------------------+      +------------------------+      +----------------------+
```

Execution architecture:

```text
User prompt
  -> LLM structured extraction
  -> Pydantic validation
  -> constraint graph normalization
  -> subdivision algorithms
  -> CadQuery shape construction
  -> DXF / STEP / GeoJSON export
  -> viewer feedback and revision loop
```

Responsibilities:

- Natural Language Layer:
  - convert ambiguous requests into typed intent
  - ask for missing values only when geometry cannot be resolved safely
- Constraint Graph:
  - canonical site representation independent of any LLM or CAD tool
  - stores parcel geometry, roads, lots, easements, utilities, zoning envelopes
- Geometry Engine:
  - deterministic construction from the constraint graph
  - uses Shapely or equivalent planar geometry for partitioning
  - uses CadQuery for robust wire/face/solid generation and STEP export
- Export Layer:
  - DXF for CAD drafting consumption
  - STEP for geometric interchange
  - GeoJSON for GIS and browser overlays
- Visualization Layer:
  - browser preview for fast iteration
  - AutoCAD/Civil 3D handoff for domain review

## 3. Constraint Representation Layer

The boundary between AI and geometry should be a typed JSON document, not raw CadQuery code. That gives validation, reproducibility, and room for deterministic optimization.

Example schema:

```json
{
  "site_id": "parcel-001",
  "units": "feet",
  "parcel": {
    "boundary": [[0, 0], [660, 0], [660, 660], [0, 660]],
    "area_acres": 10.0,
    "frontage_edges": ["south"],
    "topography": null
  },
  "roads": [
    {
      "id": "road-1",
      "type": "collector",
      "centerline": [[330, 0], [330, 660]],
      "width_ft": 40.0,
      "sidewalk_ft": 5.0,
      "row_ft": 60.0
    }
  ],
  "lots": {
    "target_count": 24,
    "min_area_sqft": 6000,
    "min_frontage_ft": 50,
    "product_mix": []
  },
  "setbacks": {
    "front_ft": 20,
    "side_ft": 5,
    "rear_ft": 15
  },
  "easements": [
    {
      "type": "utility",
      "reference": "road-1",
      "offset_ft": 20,
      "width_ft": 10
    }
  ],
  "utilities": [
    {
      "type": "water",
      "corridor_reference": "road-1"
    }
  ],
  "zoning": {
    "district": "R-1",
    "max_density_du_per_acre": 3.0
  }
}
```

Constraint flow:

1. LLM extracts intent into the schema.
2. Validation normalizes units, orientation labels, defaults, and missing fields.
3. The planner expands high-level requests into explicit geometry targets.
4. Subdivision algorithms compute parcel partitions, road corridors, setbacks, and easement buffers.
5. CadQuery receives explicit polygons, wires, and extrusion depths rather than vague natural language.

## 4. Geometry Generation Strategy

Core algorithm stack:

- Parcel normalization:
  - ingest polygon from GIS or synthesize one from area and shape
  - orient consistently and remove self-intersections
- Road skeleton generation:
  - start with one or more centerlines from intent
  - build road polygons with offset operations from centerlines
  - later phases: graph-based routing, cul-de-sacs, T intersections, and frontage checks
- Lot subdivision:
  - prototype: rectangular strip partitioning and grid fill
  - next: split polygons by centerline corridors and recursively cut into lots
  - later: objective-driven partitioning for frontage, minimum area, and yield
- Easements and utility corridors:
  - offset road edges or centerlines to generate buffers
  - clip buffers against the parcel and reserved areas

Algorithms by feature:

- Grid subdivision:
  - compute developable strips after removing road and easement corridors
  - distribute target lot count across strips proportional to developable area
  - partition strips into rows and columns to approximate equal-area lots
- Road skeleton generation:
  - represent roads as polyline centerlines
  - generate pavement from half-width offsets on both sides
  - create intersections by boolean union of corridor solids / polygons
- Offset polygons:
  - use planar geometry for setbacks, sidewalks, and no-build envelopes
  - CadQuery can reconstruct these offsets as wires/faces after the planar solver finalizes them
- Utility corridor buffers:
  - generate parallel bands from road edges or centerlines
  - preserve topology so later utilities can route inside reserved space

How CadQuery fits the shape build:

- parcel boundary -> `Workplane("XY").polyline(...).close()`
- road corridor -> polyline or face from offset boundary
- lot polygons -> repeated closed profiles generated from solver output
- easements -> additional closed profiles
- 3D site model preview -> thin extrusions for parcel, roads, and envelopes
- boolean composition -> combine intersections, subtract road space from blocks, form compounds for export

Recommended implementation split:

- planar topology and clipping: Shapely or another 2D computational geometry library
- robust B-rep and interchange solids: CadQuery/OpenCascade

## 5. Prototype Roadmap

### Phase 1: 3-hour prototype

Scope:

- natural language prompt -> constraint JSON
- rectangular parcel synthesis from acreage
- one north-south or east-west road
- simple lot grid on both sides
- easement bands
- DXF export

Deliverable:

- CLI demo that generates `subdivision_layout.dxf` in under 10 seconds

### Phase 2: 2-week prototype

Scope:

- ingest parcel boundary from GeoJSON or shapefile
- support irregular polygons
- centerline-based road generation inside arbitrary parcels
- lot geometry clipping against parcel edges
- optional STEP export through CadQuery

Deliverable:

- reproducible geometry pipeline for real parcel footprints

### Phase 3: MVP

Scope:

- zoning validation engine
- frontage, minimum lot area, and setback checks
- lot yield optimization loop
- utility corridor placement
- browser viewer with revision cycle

Deliverable:

- land-acquisition workflow where analysts can explore feasible yield quickly

### Phase 4: Full system

Scope:

- topography ingestion
- drainage and grading envelopes
- road vertical geometry and profiles
- earthwork and cut/fill estimates
- utility network sizing and conflict detection

Deliverable:

- pre-concept civil design assistant, still subject to licensed engineer review

## 6. Code Architecture

Recommended Python package structure:

```text
src/
  ai/
    parser.py
    prompts.py
    repair.py
  constraints/
    schema.py
    normalization.py
    validation.py
  geometry/
    primitives.py
    topology.py
    offsets.py
    clipping.py
  generators/
    parcel.py
    roads.py
    lots.py
    easements.py
    utilities.py
  cad/
    cadquery_adapter.py
    assemblies.py
    step_export.py
  export/
    dxf_writer.py
    geojson_writer.py
    step_writer.py
  optimization/
    objective.py
    search.py
    scoring.py
  api/
    cli.py
    service.py
```

Responsibilities:

- `ai/`: structured extraction, prompt repair, ambiguity handling
- `constraints/`: canonical schema and deterministic validation
- `geometry/`: geometry utilities that are independent of any CAD kernel
- `generators/`: domain algorithms for roads, lots, easements, utilities
- `cad/`: CadQuery-specific build logic and assembly/export integration
- `export/`: CAD and GIS format writers
- `optimization/`: yield and compliance scoring
- `api/`: CLI and service entry points

## 7. CadQuery Integration Layer

CadQuery should be wrapped behind a dedicated adapter so the rest of the system speaks in parcel, road, lot, and easement objects, not raw `Workplane` chains.

Pseudo-code:

```python
import cadquery as cq

def face_from_polygon(points):
    return cq.Workplane("XY").polyline(points).close()

def solid_from_polygon(points, thickness=1.0):
    return face_from_polygon(points).extrude(thickness)

def build_site_model(site):
    assy = cq.Assembly(name="subdivision")

    parcel = solid_from_polygon(site["parcel"]["boundary"], thickness=0.5)
    assy.add(parcel, name="parcel")

    for road in site["roads"]:
        road_solid = solid_from_polygon(road["polygon"], thickness=1.0)
        assy.add(road_solid, name=road["id"])

    for lot in site["lots"]:
        lot_face = solid_from_polygon(lot["polygon"], thickness=0.25)
        assy.add(lot_face, name=lot["id"])

    for easement in site["easements"]:
        easement_face = solid_from_polygon(easement["polygon"], thickness=0.1)
        assy.add(easement_face, name=easement["id"])

    return assy

def export_outputs(site, step_path):
    assy = build_site_model(site)
    assy.save(step_path)
```

Integration rules:

- never let the LLM emit direct CadQuery code as the first execution path
- generate typed geometry first, then compile to CadQuery
- persist both the constraint JSON and the generated CadQuery script for auditability

## 8. Civil Design Challenges

Difficult engineering problems:

- irregular parcels:
  - lots must clip cleanly to boundaries and preserve frontage
  - CadQuery can model the resulting polygons, but it will not decide legal parcelization
- road connectivity:
  - subdivision roads require graph logic, intersection design, and frontage accounting
  - CadQuery can represent corridor solids after the routing logic decides the graph
- topography:
  - grading and drainage depend on surfaces, slopes, and hydrology
  - CadQuery can represent triangulated or lofted terrain, but not perform civil grading logic alone
- drainage:
  - detention, overland flow, and utility conflict checks require simulation and engineering standards
  - this is outside CadQuery’s native problem space

What CadQuery can solve:

- deterministic geometric construction
- boolean cleanup of solids and wires
- reproducible export-ready shapes
- STEP-friendly 3D site envelopes

What CadQuery cannot solve by itself:

- zoning interpretation
- parcel yield optimization
- roadway design standards
- hydrology, stormwater, and grading compliance
- GIS CRS correctness and cadastral data management

## 9. Performance Considerations

Large subdivision layouts introduce three performance pressures:

- geometry complexity:
  - hundreds of lots create many wires, faces, and booleans
  - naive repeated boolean operations will dominate runtime
- B-rep performance:
  - OpenCascade is robust but expensive compared with pure 2D polygon operations
  - use planar libraries for partitioning, reserve CadQuery for final construction and export
- export size:
  - DXF with many polylines remains manageable, but STEP assemblies can become large quickly
  - avoid generating unnecessary 3D thickness for early planning exports

Practical guidance:

- keep the optimization loop in 2D
- compile only winning candidates into CadQuery
- use compounds/assemblies instead of repeated global unions when possible
- cache parcel normalization and road-corridor calculations
- separate preview fidelity from export fidelity

## 10. Future AI Extensions

LLMs can extend the system in three distinct ways:

- direct intent extraction:
  - translate a planner’s narrative into typed constraints and follow-up questions
- layout optimization:
  - propose alternative road graphs, lot counts, and product mixes, then score them with deterministic rules
- code generation:
  - synthesize CadQuery or geometry-generator code for human review, not direct execution without validation

Near-term AI opportunities:

- retrieve zoning rules and convert them into machine-checkable constraints
- rank alternative loting strategies by yield, frontage compliance, and road length
- generate explanation traces for why a site failed or passed constraints

On direct CAD-code generation:

- emerging LLM work shows that code models can generate parametric CAD scripts from text
- for this domain, the safer approach is constrained generation into JSON plus deterministic geometry compilation
- direct CadQuery code generation becomes useful later as a power-user authoring mode or for internal tool acceleration

## Shipping Guidance

How CadQuery fits:

- as the solid-model and interchange backend after planar site geometry is solved
- as a parametric script layer that can regenerate identical geometry from the same site JSON

What must be built around it:

- LLM extraction and repair
- typed constraint graph
- 2D computational geometry and clipping
- zoning and civil-rule engines
- CAD/GIS export layer

How quickly a prototype can ship:

- a working CLI DXF demo can ship in hours
- a parcel-aware prototype with irregular boundaries is a 1 to 2 week effort
- a usable acquisition-intelligence MVP is a multi-sprint system, with CadQuery as one component rather than the whole stack
