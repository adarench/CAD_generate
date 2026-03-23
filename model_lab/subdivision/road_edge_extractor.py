"""
Road Edge Extractor — model_lab

Converts a ProposedGraph (or raw centerlines) into oriented RoadSegment
objects with shapely geometry, ready for the buildable strip computation.

Each RoadSegment carries:
  - shapely LineString geometry
  - unit direction vector (dx, dy)
  - perpendicular normal (nx, ny)  [points left of travel direction]
  - length_ft
  - originating edge metadata

No production code is modified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import LineString


@dataclass
class RoadSegment:
    """A single oriented road segment with precomputed geometry."""

    line:        LineString           # full shapely geometry
    start:       Tuple[float, float]  # (x, y)
    end:         Tuple[float, float]  # (x, y)
    length_ft:   float
    dx:          float                # unit direction x
    dy:          float                # unit direction y
    nx:          float                # left normal x  (-dy)
    ny:          float                # left normal y  (+dx)
    edge_id:     int = -1
    from_node:   int = -1
    to_node:     int = -1

    def offset_line(self, distance_ft: float) -> Optional[LineString]:
        """
        Return a line offset by distance_ft to the left (positive) or right (negative).
        Uses shapely 2.x offset_curve API.
        """
        try:
            result = self.line.offset_curve(distance_ft)
            if result is None or result.is_empty:
                return None
            # offset_curve may return MultiLineString; take longest
            if result.geom_type == "MultiLineString":
                result = max(result.geoms, key=lambda g: g.length)
            return result
        except Exception:
            return None

    def interpolate_point(self, distance_ft: float) -> Tuple[float, float]:
        """Point along the segment at arc-distance distance_ft from start."""
        pt = self.line.interpolate(min(distance_ft, self.length_ft))
        return (pt.x, pt.y)

    def normal_at(self, distance_ft: float, side: float = 1.0) -> Tuple[float, float]:
        """Unit normal direction at arc-distance, scaled by side (+1=left, -1=right)."""
        return (self.nx * side, self.ny * side)


def _make_segment(
    coords: List[Tuple[float, float]],
    edge_id: int = -1,
    from_node: int = -1,
    to_node: int = -1,
) -> Optional[RoadSegment]:
    """Create a RoadSegment from a coordinate list."""
    if len(coords) < 2:
        return None
    line = LineString(coords)
    length = line.length
    if length < 1.0:
        return None

    # Direction from first to last point (simplified — ignores interior bends)
    x0, y0 = coords[0]
    xl, yl = coords[-1]
    dx = xl - x0
    dy = yl - y0
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1e-9:
        dx, dy = 1.0, 0.0
        dist = 1.0
    ux, uy = dx / dist, dy / dist
    # Left normal
    nx, ny = -uy, ux

    return RoadSegment(
        line=line,
        start=(x0, y0),
        end=(xl, yl),
        length_ft=length,
        dx=ux,
        dy=uy,
        nx=nx,
        ny=ny,
        edge_id=edge_id,
        from_node=from_node,
        to_node=to_node,
    )


def extract_segments_from_proposed_graph(graph) -> List[RoadSegment]:
    """
    Extract RoadSegments from a ProposedGraph.

    Each graph edge becomes one RoadSegment.
    Short edges (< 5 ft) are skipped.
    """
    segments = []
    for edge in graph.edges:
        if len(edge.coords) < 2:
            continue
        seg = _make_segment(
            [(float(x), float(y)) for x, y in edge.coords],
            edge_id=0,
            from_node=edge.from_node,
            to_node=edge.to_node,
        )
        if seg and seg.length_ft >= 5.0:
            segments.append(seg)
    return segments


def extract_segments_from_centerlines(centerlines: list) -> List[RoadSegment]:
    """
    Extract RoadSegments from a list of shapely LineStrings
    (e.g. from StreetNetworkCandidate.centerlines).
    """
    segments = []
    for i, line in enumerate(centerlines):
        if not isinstance(line, LineString) or line.length < 5.0:
            continue
        coords = list(line.coords)
        seg = _make_segment(coords, edge_id=i)
        if seg:
            segments.append(seg)
    return segments
