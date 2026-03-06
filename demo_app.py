from __future__ import annotations

import json
import tempfile
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from ai_subdivision.ai_parser import parse_prompt
from ai_subdivision.constraints import Easement, Parcel, Road
from ai_subdivision.dxf_export import export_dxf
from ai_subdivision.geojson_export import layout_to_geojson_bytes
from ai_subdivision.geometry import export_layout_to_cadquery_step
from ai_subdivision.parcel_io import load_parcel_boundary
from ai_subdivision.subdivision import summarize_layout
from ai_subdivision.yield_optimizer import optimize_yield
from ai_subdivision.zoning import ZoningRules


DEFAULT_PROMPT = "Create a subdivision on a parcel with a collector road and utility easements."
SAMPLE_PARCEL = Path("data/sample_irregular_parcel.geojson")


def main() -> None:
    st.set_page_config(page_title="AI Subdivision Demo", layout="wide")
    st.title("AI Subdivision Demo")

    with st.sidebar:
        st.header("Inputs")
        prompt = st.text_area("Prompt", value=DEFAULT_PROMPT, height=120)
        uploaded = st.file_uploader("Upload Parcel GeoJSON", type=["geojson", "json"])
        min_frontage = st.slider("Min Frontage (ft)", min_value=40, max_value=120, value=60, step=5)
        min_depth = st.slider("Min Depth (ft)", min_value=80, max_value=180, value=110, step=5)
        road_width = st.slider("Road Width (ft)", min_value=24, max_value=80, value=40, step=2)
        easement_width = st.slider("Easement Width (ft)", min_value=0, max_value=30, value=12, step=1)
        topology_filter = st.selectbox(
            "Topology",
            options=["all", "parallel", "spine", "loop", "culdesac"],
            index=0,
            help="Focus optimization on a specific street-network family.",
        )
        run = st.button("Generate Subdivision", type="primary", use_container_width=True)

    if run:
        layout, summary, downloads = _generate_layout(
            prompt=prompt,
            upload_bytes=uploaded.getvalue() if uploaded else None,
            min_frontage=min_frontage,
            min_depth=min_depth,
            road_width=road_width,
            easement_width=easement_width,
            topology_filter=topology_filter,
        )
        st.session_state["layout"] = layout
        st.session_state["summary"] = summary
        st.session_state["downloads"] = downloads

    if "layout" not in st.session_state:
        st.info("Upload a parcel or use the sample parcel, then click Generate Subdivision.")
        return

    layout = st.session_state["layout"]
    summary = st.session_state["summary"]
    downloads = st.session_state["downloads"]

    col_map, col_summary = st.columns([2.5, 1.2])
    with col_map:
        st.subheader("Optimized Layout")
        st.plotly_chart(_plot_layout(layout), use_container_width=True)
    with col_summary:
        st.subheader("Layout Summary")
        st.metric("Max Lot Count", int(summary["generated_lot_count"]))
        st.metric("Parcel Area (sqft)", f"{summary['parcel_area_sqft']:.0f}")
        st.metric("Developable Area (sqft)", f"{summary['developable_area_sqft']:.0f}")
        st.metric("Road Length (ft)", f"{summary['road_length_ft']:.0f}")
        st.metric("Average Lot Size (sqft)", f"{summary['average_lot_area_sqft']:.0f}")
        st.metric("Network Type", str(summary["network_type"]))

    st.subheader("Downloads")
    st.download_button("Download DXF", data=downloads["dxf"], file_name="optimized_layout.dxf")
    st.download_button("Download STEP", data=downloads["step"], file_name="optimized_layout.step")
    st.download_button("Download GeoJSON", data=downloads["geojson"], file_name="optimized_layout.geojson")


def _generate_layout(
    prompt: str,
    upload_bytes: bytes | None,
    min_frontage: int,
    min_depth: int,
    road_width: int,
    easement_width: int,
    topology_filter: str = "all",
):
    boundary = _load_boundary(upload_bytes)
    constraints = parse_prompt(prompt)
    constraints = constraints.model_copy(
        update={
            "parcel": Parcel(shape="polygon", boundary=boundary, area_acres=None, aspect_ratio=1.5),
            "road": Road(orientation=constraints.road.orientation, width_ft=float(road_width)),
            "easement": Easement(width_ft=float(easement_width)),
        }
    )
    zoning_rules = ZoningRules(
        min_frontage_ft=float(min_frontage),
        min_depth_ft=float(min_depth),
        min_area_sqft=6000.0,
    )
    allowed_topologies = None if topology_filter == "all" else [topology_filter]
    optimization_result = optimize_yield(
        constraints, zoning_rules, allowed_topologies=allowed_topologies
    )
    layout = optimization_result.best_layout
    summary = summarize_layout(constraints, zoning_rules, layout)
    downloads = _build_downloads(layout)
    return layout, summary, downloads


def _load_boundary(upload_bytes: bytes | None):
    if upload_bytes is None:
        return load_parcel_boundary(str(SAMPLE_PARCEL))
    with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as handle:
        handle.write(upload_bytes)
        temp_path = handle.name
    return load_parcel_boundary(temp_path)


def _build_downloads(layout):
    geojson_bytes = layout_to_geojson_bytes(layout)
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as dxf_handle:
        dxf_path = dxf_handle.name
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as step_handle:
        step_path = step_handle.name
    export_dxf(layout, dxf_path)
    export_layout_to_cadquery_step(layout, step_path)
    return {
        "dxf": Path(dxf_path).read_bytes(),
        "step": Path(step_path).read_bytes(),
        "geojson": geojson_bytes,
    }


def _plot_layout(layout) -> go.Figure:
    fig = go.Figure()
    _add_polygons(fig, layout.parcel, color="#888888", name="Parcel", line_width=2)
    _add_polygons(fig, layout.road, color="#111111", name="Roads", line_width=2)
    _add_polygons(fig, layout.easements, color="#d62728", name="Easements", line_width=1)
    _add_polygons(fig, layout.lots, color="#1f77b4", name="Lots", line_width=1)
    for label in layout.lot_labels:
        fig.add_trace(
            go.Scatter(
                x=[label.position[0]],
                y=[label.position[1]],
                mode="text",
                text=[label.text],
                textposition="middle center",
                showlegend=False,
                hoverinfo="skip",
            )
        )
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False),
        legend=dict(orientation="h"),
    )
    return fig


def _add_polygons(fig: go.Figure, polygons, color: str, name: str, line_width: int) -> None:
    for index, polygon in enumerate(polygons):
        coords = polygon.closed_points()
        xs = [point[0] for point in coords]
        ys = [point[1] for point in coords]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                fill="toself",
                fillcolor=_rgba(color, 0.15),
                line=dict(color=color, width=line_width),
                name=name if index == 0 else name,
                showlegend=index == 0,
            )
        )


def _rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


if __name__ == "__main__":
    main()
