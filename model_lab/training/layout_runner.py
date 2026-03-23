"""
Layout Runner — model_lab

Bridges a ParcelSample + LayoutStrategy → LayoutResult by:
  1. Converting geographic coordinates (lng/lat) to local feet when needed
  2. Building SubdivisionConstraints from the parcel boundary
  3. Selecting the appropriate street network candidate for the requested topology
  4. Calling the deterministic layout engine
  5. Extracting the road graph from centerlines
  6. Returning structured metrics + road graph

No production code is modified.  ai_subdivision is imported read-only.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Production imports (read-only)
# ---------------------------------------------------------------------------
from ai_subdivision.constraints import Easement, Lots, Parcel, Road, SubdivisionConstraints
from ai_subdivision.geometry import parcel_shapely_from_constraints
from ai_subdivision.street_network import generate_candidate_street_networks
from ai_subdivision.subdivision import generate_subdivision, summarize_layout
from ai_subdivision.zoning import ZoningRules

# ---------------------------------------------------------------------------
# Model lab imports
# ---------------------------------------------------------------------------
from model_lab.strategy_models.strategy_interface import LayoutStrategy
from model_lab.training.parcel_loader import ParcelSample
from model_lab.training.road_graph_extractor import RoadGraph, extract_road_graph

# ParamStrategy imported lazily to avoid circular imports

# ---------------------------------------------------------------------------
# Geometry projection helpers (inline — avoids importing from apps/python-api/)
# ---------------------------------------------------------------------------
FEET_PER_DEGREE_LAT = 364000.0


def _geographic_to_feet(
    coordinates: List[List[float]],
) -> Tuple[List[Tuple[float, float]], dict]:
    """
    Project a WGS84 polygon ring (lng/lat degrees) to local feet.

    Returns:
        (local_boundary_ft, projection_info_dict)
    """
    lngs = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    origin_lng = sum(lngs) / len(lngs)
    origin_lat = sum(lats) / len(lats)
    feet_per_deg_lng = max(FEET_PER_DEGREE_LAT * math.cos(math.radians(origin_lat)), 1.0)

    projection = {
        "origin_lng": origin_lng,
        "origin_lat": origin_lat,
        "feet_per_deg_lng": feet_per_deg_lng,
        "feet_per_deg_lat": FEET_PER_DEGREE_LAT,
    }

    local_boundary = [
        (
            (lng - origin_lng) * feet_per_deg_lng,
            (lat - origin_lat) * FEET_PER_DEGREE_LAT,
        )
        for lng, lat in [(c[0], c[1]) for c in coordinates]
    ]
    return local_boundary, projection


def _extract_exterior_ring(geometry_geojson: dict) -> List[List[float]]:
    """Extract the exterior ring from a GeoJSON Polygon or MultiPolygon."""
    geom_type = geometry_geojson.get("type", "")
    coords = geometry_geojson.get("coordinates", [])
    if geom_type == "Polygon":
        ring = coords[0] if coords else []
    elif geom_type == "MultiPolygon":
        ring = max(coords, key=lambda poly: len(poly[0]))[0]
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")
    if ring and ring[0] == ring[-1]:
        ring = ring[:-1]
    return ring


# ---------------------------------------------------------------------------
# Density → target lot count
# ---------------------------------------------------------------------------

DENSITY_TO_LOT_MULTIPLIER = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.6,
}

DEFAULT_ROAD_WIDTH_FT = 40.0
DEFAULT_EASEMENT_WIDTH_FT = 10.0
DEFAULT_ZONING = ZoningRules(
    min_frontage_ft=60.0,
    min_depth_ft=110.0,
    min_area_sqft=6000.0,
)


def _density_to_lot_count(area_sqft: float, density_goal: str) -> int:
    base = int(area_sqft / DEFAULT_ZONING.min_area_sqft)
    multiplier = DENSITY_TO_LOT_MULTIPLIER.get(density_goal, 1.0)
    return max(4, min(int(base * multiplier), 60))


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LayoutMetrics:
    """Structured layout output — dimensions, network metadata, and graph metrics."""

    # Lot / area metrics
    lot_count: int
    avg_lot_area_sqft: float
    road_length_ft: float
    developable_area_sqft: float
    parcel_area_sqft: float
    road_width_ft: float

    # Network metadata
    network_topology: str
    network_orientation: str
    road_offset_ft: float
    road_count: int

    # Graph metrics (from road_graph_extractor)
    graph_node_count: int = 0
    graph_edge_count: int = 0
    intersection_count: int = 0
    dead_end_count: int = 0
    avg_edge_length_ft: float = 0.0
    max_edge_length_ft: float = 0.0
    road_density_ft_per_acre: float = 0.0
    graph_diameter: int = 0

    def to_dict(self) -> dict:
        return {
            # Lot / area
            "lot_count": self.lot_count,
            "avg_lot_area_sqft": round(self.avg_lot_area_sqft, 2),
            "road_length_ft": round(self.road_length_ft, 2),
            "developable_area_sqft": round(self.developable_area_sqft, 2),
            "parcel_area_sqft": round(self.parcel_area_sqft, 2),
            "road_width_ft": self.road_width_ft,
            # Network
            "network_topology": self.network_topology,
            "network_orientation": self.network_orientation,
            "road_offset_ft": self.road_offset_ft,
            "road_count": self.road_count,
            # Graph
            "graph_node_count": self.graph_node_count,
            "graph_edge_count": self.graph_edge_count,
            "intersection_count": self.intersection_count,
            "dead_end_count": self.dead_end_count,
            "avg_edge_length_ft": round(self.avg_edge_length_ft, 2),
            "max_edge_length_ft": round(self.max_edge_length_ft, 2),
            "road_density_ft_per_acre": round(self.road_density_ft_per_acre, 4),
            "graph_diameter": self.graph_diameter,
        }


@dataclass
class LayoutResult:
    """
    Full output of a single layout simulation.

    Contains structured metrics AND the road graph for ML training.
    """
    metrics: LayoutMetrics
    road_graph: RoadGraph


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_layout(
    parcel: ParcelSample,
    strategy: LayoutStrategy,
    zoning: Optional[ZoningRules] = None,
) -> LayoutResult:
    """
    Execute the layout engine for a single (parcel, strategy) combination.

    Returns LayoutResult (metrics + road_graph) on success.
    Raises ValueError on unrecoverable geometry failures.
    Production code is never modified — this is a pure consumer.
    """
    active_zoning = zoning or DEFAULT_ZONING

    # 1. Get exterior ring
    try:
        ring = _extract_exterior_ring(parcel.geometry_geojson)
    except (ValueError, IndexError, KeyError) as exc:
        raise ValueError(f"Could not extract ring from parcel {parcel.parcel_id}: {exc}") from exc

    if len(ring) < 3:
        raise ValueError(f"Parcel {parcel.parcel_id} has fewer than 3 vertices")

    # 2. Convert to local feet if geographic
    if parcel.is_geographic:
        boundary_ft, _ = _geographic_to_feet(ring)
    else:
        boundary_ft = [(float(c[0]), float(c[1])) for c in ring]

    # 3. Compute usable area for lot-count targeting
    from shapely.geometry import Polygon as _Poly
    local_poly = _Poly(boundary_ft)
    area_sqft = float(local_poly.area)
    if area_sqft < 10000:
        raise ValueError(
            f"Parcel {parcel.parcel_id} footprint too small ({area_sqft:.0f} sqft) after projection"
        )

    # 4. Build SubdivisionConstraints
    target_lots = _density_to_lot_count(area_sqft, strategy.density_goal)
    road_orientation = (
        "north_south" if strategy.entry_point in ("north", "south") else "east_west"
    )
    constraints = SubdivisionConstraints(
        parcel=Parcel(shape="polygon", boundary=boundary_ft),
        lots=Lots(count=target_lots),
        road=Road(orientation=road_orientation, width_ft=DEFAULT_ROAD_WIDTH_FT),
        easement=Easement(width_ft=DEFAULT_EASEMENT_WIDTH_FT),
    )

    # 5. Generate candidate street networks and select by topology
    parcel_polygon = parcel_shapely_from_constraints(constraints)
    candidates = generate_candidate_street_networks(
        parcel_polygon=parcel_polygon,
        road_width_ft=DEFAULT_ROAD_WIDTH_FT,
    )

    matching = [c for c in candidates if c.topology == strategy.road_type]
    if not matching:
        matching = [c for c in candidates if c.topology == "collector"]
    if not matching:
        matching = candidates
    if not matching:
        raise ValueError(f"No street network candidates for parcel {parcel.parcel_id}")

    # Pick candidate with the most road coverage
    network = max(matching, key=lambda c: c.road_length_ft)

    # 6. Run layout engine
    layout = generate_subdivision(
        constraints=constraints,
        zoning_rules=active_zoning,
        street_network=network,
        target_lot_count=target_lots,
    )

    # 7. Extract road graph from centerlines
    road_graph = extract_road_graph(
        centerlines=network.centerlines,
        parcel_area_sqft=area_sqft,
    )

    # 8. Compute summary metrics
    summary = summarize_layout(constraints, active_zoning, layout)
    gm = road_graph.metrics

    metrics = LayoutMetrics(
        # Lot / area
        lot_count=summary["generated_lot_count"],
        avg_lot_area_sqft=float(summary["average_lot_area_sqft"]),
        road_length_ft=float(summary["road_length_ft"]),
        developable_area_sqft=float(summary["developable_area_sqft"]),
        parcel_area_sqft=float(summary["parcel_area_sqft"]),
        road_width_ft=DEFAULT_ROAD_WIDTH_FT,
        # Network
        network_topology=network.topology,
        network_orientation=network.orientation,
        road_offset_ft=float(network.metadata.get("offset_ft", 0.0)),
        road_count=int(network.metadata.get("road_count", 1)),
        # Graph
        graph_node_count=gm.node_count,
        graph_edge_count=gm.edge_count,
        intersection_count=gm.intersection_count,
        dead_end_count=gm.dead_end_count,
        avg_edge_length_ft=gm.avg_edge_length_ft,
        max_edge_length_ft=gm.max_edge_length_ft,
        road_density_ft_per_acre=gm.road_density_ft_per_acre,
        graph_diameter=gm.graph_diameter,
    )

    return LayoutResult(metrics=metrics, road_graph=road_graph)


# ---------------------------------------------------------------------------
# Parameterized runner — accepts ParamStrategy
# ---------------------------------------------------------------------------

def run_layout_param(
    parcel: ParcelSample,
    param_strategy,   # ParamStrategy — typed loosely to avoid circular import
    zoning: Optional[ZoningRules] = None,
) -> Optional[LayoutResult]:
    """
    Execute the layout engine using a ParamStrategy's full parameter set.

    Uses param_strategy.road_width_ft, min_lot_area_sqft, min_frontage_ft,
    min_depth_ft, and target_density_du_per_acre in place of the fixed defaults.

    Returns LayoutResult on success, None on unrecoverable failure.
    """
    # 1. Get exterior ring
    try:
        ring = _extract_exterior_ring(parcel.geometry_geojson)
    except (ValueError, IndexError, KeyError):
        return None

    if len(ring) < 3:
        return None

    # 2. Project to feet
    if parcel.is_geographic:
        boundary_ft, _ = _geographic_to_feet(ring)
    else:
        boundary_ft = [(float(c[0]), float(c[1])) for c in ring]

    # 3. Area check
    from shapely.geometry import Polygon as _Poly
    local_poly = _Poly(boundary_ft)
    area_sqft = float(local_poly.area)
    if area_sqft < 10000:
        return None

    # 4. Build engine params from ParamStrategy
    engine_params = param_strategy.to_engine_params(area_sqft)
    target_lots   = engine_params["target_lot_count"]
    road_w        = engine_params["road_width_ft"]

    active_zoning = zoning or ZoningRules(
        min_frontage_ft=engine_params["min_frontage_ft"],
        min_depth_ft=engine_params["min_depth_ft"],
        min_area_sqft=engine_params["min_lot_area_sqft"],
    )

    # 5. Build constraints
    constraints = SubdivisionConstraints(
        parcel=Parcel(shape="polygon", boundary=boundary_ft),
        lots=Lots(count=target_lots),
        road=Road(orientation=engine_params["road_orientation"], width_ft=road_w),
        easement=Easement(width_ft=DEFAULT_EASEMENT_WIDTH_FT),
    )

    # 6. Generate and select network candidate
    parcel_polygon = parcel_shapely_from_constraints(constraints)
    try:
        candidates = generate_candidate_street_networks(
            parcel_polygon=parcel_polygon,
            road_width_ft=road_w,
        )
    except Exception:
        return None

    road_type = engine_params["road_type"]
    matching  = [c for c in candidates if c.topology == road_type]
    if not matching:
        matching = [c for c in candidates if c.topology == "collector"]
    if not matching:
        matching = candidates
    if not matching:
        return None

    network = max(matching, key=lambda c: c.road_length_ft)

    # 7. Run engine
    try:
        layout = generate_subdivision(
            constraints=constraints,
            zoning_rules=active_zoning,
            street_network=network,
            target_lot_count=target_lots,
        )
    except Exception:
        return None

    # 8. Extract road graph
    road_graph = extract_road_graph(
        centerlines=network.centerlines,
        parcel_area_sqft=area_sqft,
    )

    # 9. Metrics
    summary = summarize_layout(constraints, active_zoning, layout)
    gm = road_graph.metrics

    metrics = LayoutMetrics(
        lot_count=summary["generated_lot_count"],
        avg_lot_area_sqft=float(summary["average_lot_area_sqft"]),
        road_length_ft=float(summary["road_length_ft"]),
        developable_area_sqft=float(summary["developable_area_sqft"]),
        parcel_area_sqft=float(summary["parcel_area_sqft"]),
        road_width_ft=road_w,
        network_topology=network.topology,
        network_orientation=network.orientation,
        road_offset_ft=float(network.metadata.get("offset_ft", 0.0)),
        road_count=int(network.metadata.get("road_count", 1)),
        graph_node_count=gm.node_count,
        graph_edge_count=gm.edge_count,
        intersection_count=gm.intersection_count,
        dead_end_count=gm.dead_end_count,
        avg_edge_length_ft=gm.avg_edge_length_ft,
        max_edge_length_ft=gm.max_edge_length_ft,
        road_density_ft_per_acre=gm.road_density_ft_per_acre,
        graph_diameter=gm.graph_diameter,
    )

    return LayoutResult(metrics=metrics, road_graph=road_graph)
