# AI Subdivision Generator Prototype

This repository contains a CLI prototype that turns a natural-language subdivision prompt into:

- validated constraint JSON
- a generated subdivision layout
- an AutoCAD-compatible DXF file

The working demo uses a simple geometry model:

- rectangular parcel centered at the origin
- one central road
- equal-area rectangular lots on both sides of the road
- utility easement bands adjacent to the road

Phase 2 extends this with:

- parcel import from GeoJSON polygon boundaries
- road corridors clipped to irregular parcels
- lot polygons sliced and clipped against the actual parcel shape

The current engine also supports frontage-aware lot generation:

- frontage extracted from developable land adjacent to the road corridor
- lot segmentation by minimum frontage width
- perpendicular lot templates clipped to the developable polygon
- zoning-rule filtering by frontage, depth, and area
- DXF lot labels on a `LOT_LABELS` layer

## Project Structure

```text
ai_subdivision/
  main.py
  ai_parser.py
  constraints.py
  geometry.py
  subdivision.py
  dxf_export.py
  street_network.py
  yield_optimizer.py
demo_app.py
main.py
requirements.txt
docs/cadquery_landdev_roadmap.md
```

## Dependencies

The prototype is designed to run in two modes:

1. Full mode with `openai`, `numpy`, `pydantic`, `shapely`, `ezdxf`, and optionally `cadquery`
2. Fallback mode with only `openai`, `numpy`, and `pydantic`

Fallback mode still parses prompts locally and writes a valid ASCII DXF file without `shapely`, `ezdxf`, or `cadquery`.

## Install

```bash
python3 -m pip install -r requirements.txt
```

## Run

```bash
python3 main.py "Create a subdivision on a 10 acre rectangular parcel with 24 lots, a main road running north south, and 10 foot utility easements along the road."
```

If no prompt argument is provided, the CLI will prompt interactively.

Phase 2 irregular parcel example:

```bash
python3 main.py \
  "Create a subdivision on a 12 acre parcel with 28 lots, a north-south collector road, and 12 foot utility easements along the road." \
  --parcel-geojson data/sample_irregular_parcel.geojson \
  --output phase2_irregular.dxf \
  --step phase2_irregular.step
```

Custom zoning rules:

```bash
python3 main.py \
  "Create a subdivision on a 10 acre parcel with 24 lots and a north south road." \
  --zoning-rules zoning_rules.json
```

Yield optimization:

```bash
python3 main.py \
  "Create a subdivision on a 12 acre parcel with a collector road and 12 foot utility easements" \
  --parcel-geojson data/sample_irregular_parcel.geojson \
  --optimize \
  --output optimized_layout.dxf
```

Topology-focused optimization:

```bash
python3 main.py \
  "Create a subdivision on a 12 acre parcel with loop streets" \
  --parcel-geojson data/sample_irregular_parcel.geojson \
  --optimize \
  --topology loop \
  --output optimized_loop.dxf
```

Interactive UI demo:

```bash
python3 -m streamlit run demo_app.py
```

The UI now exposes a topology filter (`all`, `parallel`, `spine`, `loop`, `culdesac`) that guides which street-network candidates the optimizer evaluates, and the console output lists each tested topology with its lot count and road length.

## Output

The command writes:

- `subdivision_constraints.json`
- `subdivision_layout.dxf`
- optional lot labels on `LOT_LABELS`
- optional GeoJSON export through the demo app

The DXF contains these layers:

- `PARCEL`
- `ROAD`
- `OPT_ROAD` for optimized road layouts
- `LOT_LINES`
- `EASEMENTS`

Optional STEP export through CadQuery:

```bash
python3 main.py "Create a 12 acre subdivision with 30 lots and a north south road." --step subdivision_layout.step
```

## Example Prompt

```text
Create a subdivision on a 12 acre parcel with 28 lots, a north-south collector road, sidewalks, and utility easements along the road.
```

Sample parcel file:

- `data/sample_irregular_parcel.geojson`
- `zoning_rules.json`

## Notes

- The OpenAI parser is used only when `OPENAI_API_KEY` is set. Otherwise the CLI uses a local regex parser.
- Parcel import currently supports GeoJSON `Polygon` geometry only.
- Frontage-aware lot generation is deterministic and zoning-filtered, but still intended for early feasibility work rather than final engineering parcelization.
- If the requested lot count exceeds frontage/zoning capacity, the engine returns the feasible count instead of creating noncompliant lots.
- The optimizer now evaluates procedural street networks including spine, parallel, loop, and cul-de-sac candidates.
- Optional CadQuery export is available through `--step` and is implemented in `ai_subdivision/geometry.py`.
