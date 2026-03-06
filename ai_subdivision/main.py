from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ai_parser import parse_prompt
from .constraints import Parcel
from .dxf_export import export_dxf
from .geometry import export_layout_to_cadquery_step
from .parcel_io import load_parcel_boundary
from .subdivision import generate_subdivision, summarize_layout
from .yield_optimizer import optimize_yield
from .zoning import load_zoning_rules


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a subdivision DXF from a text prompt.")
    parser.add_argument("prompt", nargs="*", help="Natural language subdivision prompt.")
    parser.add_argument(
        "--output",
        default="subdivision_layout.dxf",
        help="Path to the output DXF file.",
    )
    parser.add_argument(
        "--json",
        default="subdivision_constraints.json",
        help="Path to write extracted constraints JSON.",
    )
    parser.add_argument(
        "--step",
        default="",
        help="Optional path to export a CadQuery STEP model.",
    )
    parser.add_argument(
        "--parcel-geojson",
        default="",
        help="Optional GeoJSON polygon to use as the parcel boundary.",
    )
    parser.add_argument(
        "--zoning-rules",
        default="",
        help="Optional path to a zoning rules JSON file.",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Explore multiple road placements and export the highest-yield layout.",
    )
    parser.add_argument(
        "--topology",
        choices=["all", "parallel", "spine", "loop", "culdesac"],
        default="all",
        help="Limit optimizer to a specific topology family.",
    )
    args = parser.parse_args()

    prompt = " ".join(args.prompt).strip()
    if not prompt:
        prompt = input("Enter subdivision prompt: ").strip()
    if not prompt:
        raise SystemExit("A prompt is required.")

    constraints = parse_prompt(prompt)
    if args.parcel_geojson:
        boundary = load_parcel_boundary(args.parcel_geojson)
        constraints = constraints.model_copy(
            update={
                "parcel": Parcel(
                    shape="polygon",
                    boundary=boundary,
                    area_acres=None,
                    aspect_ratio=constraints.parcel.aspect_ratio,
                )
            }
        )
    zoning_rules = load_zoning_rules(args.zoning_rules or None)
    optimization_result = None
    allowed_topologies = None if args.topology == "all" else [args.topology]
    if args.optimize:
        optimization_result = optimize_yield(
            constraints, zoning_rules, allowed_topologies=allowed_topologies
        )
        layout = optimization_result.best_layout
    else:
        layout = generate_subdivision(constraints, zoning_rules)

    json_path = Path(args.json)
    json_path.write_text(
        json.dumps(constraints.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    dxf_path = export_dxf(layout, output_path=args.output)
    step_path = ""
    if args.step:
        step_path = export_layout_to_cadquery_step(layout, path=args.step)

    summary = summarize_layout(constraints, zoning_rules, layout)
    if optimization_result is not None:
        print("Optimization Results")
        print("--------------------")
        print(f"Layouts tested: {optimization_result.layouts_tested}")
        print(f"Best lot count: {optimization_result.lot_count}")
        print(f"Network type: {optimization_result.best_network.topology}")
        print(f"Road orientation: {optimization_result.best_network.orientation}")
        if "offset_ft" in optimization_result.best_network.metadata:
            print(f"Road offset: {optimization_result.best_network.metadata['offset_ft']:.0f} ft")
        if "road_count" in optimization_result.best_network.metadata:
            print(f"Road count: {int(optimization_result.best_network.metadata['road_count'])}")
        if "spacing_ft" in optimization_result.best_network.metadata:
            print(f"Road spacing: {optimization_result.best_network.metadata['spacing_ft']:.0f} ft")
    print(json.dumps(summary, indent=2))
    print(f"Constraint JSON written to {json_path}")
    print(f"DXF file written to {dxf_path}")
    if step_path:
        print(f"STEP file written to {step_path}")


if __name__ == "__main__":
    main()
