"""
Road Graph Generator — model_lab

Generates candidate road network graphs directly from parcel geometry.

Generators
----------
SpineGenerator     — collector spine + perpendicular branches (fishbone)
LoopGenerator      — perimeter loop road with optional cross-streets
GridGenerator      — regular grid (N×M)  ← novel, not in engine templates
HerringboneGenerator — diagonal branches at configurable angle ← novel
TGenerator         — T-junction: two spines meeting at centre
RadialGenerator    — hub-and-spoke radiating from parcel centre ← novel

Each generator accepts a bounding box (minx, miny, maxx, maxy) and
optional keyword overrides, and returns a ProposedGraph.

"Novel" topologies are those that cannot be expressed by the four fixed
templates (loop, spine, parallel, culdesac) in the production engine.

No production code is modified.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from model_lab.graph_models.road_graph import (
    GraphEdge,
    GraphNode,
    NODE_DEAD_END,
    NODE_ENTRY,
    NODE_INTERSECTION,
    NODE_TERMINUS,
    ProposedGraph,
)

# ---------------------------------------------------------------------------
# Bounding box helpers
# ---------------------------------------------------------------------------

BBox = Tuple[float, float, float, float]   # (minx, miny, maxx, maxy)


def _bbox_from_polygon(geojson: dict) -> BBox:
    """Compute bounding box of a GeoJSON Polygon."""
    gtype = geojson.get("type", "")
    if gtype == "Polygon":
        ring = geojson["coordinates"][0]
    elif gtype == "MultiPolygon":
        ring = max(geojson["coordinates"], key=lambda r: len(r[0]))[0]
    else:
        ring = []
    if not ring:
        return (0.0, 0.0, 100.0, 100.0)
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_from_sqft(area_sqft: float) -> BBox:
    """Synthesise a square bbox with the given area."""
    side = math.sqrt(area_sqft)
    return (0.0, 0.0, side, side)


# ---------------------------------------------------------------------------
# Node registry helper
# ---------------------------------------------------------------------------

class _NodeRegistry:
    def __init__(self) -> None:
        self._next_id = 0
        self.nodes: List[GraphNode] = []

    def add(self, x: float, y: float, ntype: str = NODE_TERMINUS) -> GraphNode:
        n = GraphNode(id=self._next_id, x=x, y=y, type=ntype)
        self._next_id += 1
        self.nodes.append(n)
        return n

    def last(self) -> GraphNode:
        return self.nodes[-1]


# ---------------------------------------------------------------------------
# 1. Spine (fishbone) generator
# ---------------------------------------------------------------------------

def generate_spine(
    bbox: BBox,
    parcel_area_sqft: float = 0.0,
    offset_ft: float = 40.0,
    branch_spacing_ft: float = 120.0,
    branch_depth_fraction: float = 0.40,
    entry_side: str = "south",
    n_branches_override: Optional[int] = None,
) -> ProposedGraph:
    """
    Spine (fishbone) road graph.

    Central collector runs the length of the parcel.
    Perpendicular branches extend on both sides at regular spacing.

    Args:
        offset_ft:             offset of spine from entry edge
        branch_spacing_ft:     distance between branches along spine
        branch_depth_fraction: how far branches extend (fraction of half-width)
        entry_side:            which parcel edge the spine enters from
    """
    minx, miny, maxx, maxy = bbox
    w = maxx - minx
    h = maxy - miny
    area = parcel_area_sqft or w * h

    reg = _NodeRegistry()

    if entry_side in ("south", "north"):
        # Spine runs E-W; branches go N-S
        spine_y  = miny + offset_ft if entry_side == "south" else maxy - offset_ft
        spine_x0 = minx + offset_ft
        spine_x1 = maxx - offset_ft
        spine_len = spine_x1 - spine_x0
        if spine_len <= 0:
            spine_x0, spine_x1 = minx + w * 0.1, maxx - w * 0.1
            spine_len = spine_x1 - spine_x0

        n_branches = n_branches_override or max(2, int(spine_len / branch_spacing_ft))
        branch_half = (h - offset_ft * 2) * branch_depth_fraction

        # Entry node
        entry = reg.add(spine_x0, miny if entry_side == "south" else maxy, NODE_ENTRY)
        spine_start = reg.add(spine_x0, spine_y, NODE_INTERSECTION)
        prev = spine_start
        edges = [GraphEdge(entry.id, spine_start.id, [(entry.x, entry.y), (spine_start.x, spine_start.y)])]

        for i in range(n_branches + 1):
            x_pos = spine_x0 + i * (spine_len / max(n_branches, 1))
            x_pos = min(x_pos, spine_x1)
            ntype = NODE_INTERSECTION if i < n_branches else NODE_DEAD_END
            cur = reg.add(x_pos, spine_y, ntype)
            edges.append(GraphEdge(prev.id, cur.id, [(prev.x, prev.y), (cur.x, cur.y)]))
            prev = cur

            if i < n_branches:
                # North branch
                nb = reg.add(x_pos, spine_y + branch_half, NODE_DEAD_END)
                edges.append(GraphEdge(cur.id, nb.id, [(cur.x, cur.y), (nb.x, nb.y)]))
                # South branch (if room)
                if spine_y - branch_half > miny:
                    sb = reg.add(x_pos, spine_y - branch_half, NODE_DEAD_END)
                    edges.append(GraphEdge(cur.id, sb.id, [(cur.x, cur.y), (sb.x, sb.y)]))
    else:
        # Spine runs N-S; branches go E-W
        spine_x  = minx + offset_ft if entry_side == "west" else maxx - offset_ft
        spine_y0 = miny + offset_ft
        spine_y1 = maxy - offset_ft
        spine_len = spine_y1 - spine_y0
        if spine_len <= 0:
            spine_y0, spine_y1 = miny + h * 0.1, maxy - h * 0.1
            spine_len = spine_y1 - spine_y0

        n_branches = n_branches_override or max(2, int(spine_len / branch_spacing_ft))
        branch_half = (w - offset_ft * 2) * branch_depth_fraction

        entry = reg.add(spine_x, miny if entry_side == "west" else maxy, NODE_ENTRY)
        spine_start = reg.add(spine_x, spine_y0, NODE_INTERSECTION)
        prev = spine_start
        edges = [GraphEdge(entry.id, spine_start.id, [(entry.x, entry.y), (spine_start.x, spine_start.y)])]

        for i in range(n_branches + 1):
            y_pos = spine_y0 + i * (spine_len / max(n_branches, 1))
            y_pos = min(y_pos, spine_y1)
            ntype = NODE_INTERSECTION if i < n_branches else NODE_DEAD_END
            cur = reg.add(spine_x, y_pos, ntype)
            edges.append(GraphEdge(prev.id, cur.id, [(prev.x, prev.y), (cur.x, cur.y)]))
            prev = cur
            if i < n_branches:
                rb = reg.add(spine_x + branch_half, y_pos, NODE_DEAD_END)
                edges.append(GraphEdge(cur.id, rb.id, [(cur.x, cur.y), (rb.x, rb.y)]))
                if spine_x - branch_half > minx:
                    lb = reg.add(spine_x - branch_half, y_pos, NODE_DEAD_END)
                    edges.append(GraphEdge(cur.id, lb.id, [(cur.x, cur.y), (lb.x, lb.y)]))

    g = ProposedGraph(
        nodes=reg.nodes, edges=edges,
        entry_points=[0],
        generator_type="spine",
        params={"offset_ft": offset_ft, "branch_spacing_ft": branch_spacing_ft,
                "branch_depth_fraction": branch_depth_fraction, "entry_side": entry_side},
        parcel_area_sqft=area,
    )
    g.compute_metrics(area)
    return g


# ---------------------------------------------------------------------------
# 2. Loop generator
# ---------------------------------------------------------------------------

def generate_loop(
    bbox: BBox,
    parcel_area_sqft: float = 0.0,
    offset_ft: float = 60.0,
    entry_side: str = "south",
    add_cross: bool = False,
) -> ProposedGraph:
    """
    Rectangular perimeter loop road.

    A loop road offset inward from the parcel boundary, with an entry
    connector from one edge. Optionally adds cross-streets through the loop.
    """
    minx, miny, maxx, maxy = bbox
    w = maxx - minx
    h = maxy - miny
    area = parcel_area_sqft or w * h

    # Loop corners
    lx0, ly0 = minx + offset_ft, miny + offset_ft
    lx1, ly1 = maxx - offset_ft, maxy - offset_ft

    if lx1 <= lx0 or ly1 <= ly0:
        offset_ft = min(w, h) * 0.12
        lx0, ly0 = minx + offset_ft, miny + offset_ft
        lx1, ly1 = maxx - offset_ft, maxy - offset_ft

    reg = _NodeRegistry()

    # Four loop corners
    sw = reg.add(lx0, ly0, NODE_INTERSECTION)
    se = reg.add(lx1, ly0, NODE_INTERSECTION)
    ne = reg.add(lx1, ly1, NODE_INTERSECTION)
    nw = reg.add(lx0, ly1, NODE_INTERSECTION)

    edges = [
        GraphEdge(sw.id, se.id, [(sw.x, sw.y), (se.x, se.y)]),
        GraphEdge(se.id, ne.id, [(se.x, se.y), (ne.x, ne.y)]),
        GraphEdge(ne.id, nw.id, [(ne.x, ne.y), (nw.x, nw.y)]),
        GraphEdge(nw.id, sw.id, [(nw.x, nw.y), (sw.x, sw.y)]),
    ]

    # Entry connector
    if entry_side == "south":
        mid_x = (lx0 + lx1) / 2.0
        mid_sw = reg.add(mid_x, ly0, NODE_INTERSECTION)
        ext = reg.add(mid_x, miny, NODE_ENTRY)
        edges.append(GraphEdge(ext.id, mid_sw.id, [(ext.x, ext.y), (mid_sw.x, mid_sw.y)]))
        # split south edge at mid
        edges = [e for e in edges if not (e.from_node == sw.id and e.to_node == se.id)]
        edges.append(GraphEdge(sw.id, mid_sw.id, [(sw.x, sw.y), (mid_sw.x, mid_sw.y)]))
        edges.append(GraphEdge(mid_sw.id, se.id, [(mid_sw.x, mid_sw.y), (se.x, se.y)]))
    elif entry_side == "west":
        mid_y = (ly0 + ly1) / 2.0
        mid_sw = reg.add(lx0, mid_y, NODE_INTERSECTION)
        ext = reg.add(minx, mid_y, NODE_ENTRY)
        edges.append(GraphEdge(ext.id, mid_sw.id, [(ext.x, ext.y), (mid_sw.x, mid_sw.y)]))
        edges = [e for e in edges if not (e.from_node == nw.id and e.to_node == sw.id)]
        edges.append(GraphEdge(nw.id, mid_sw.id, [(nw.x, nw.y), (mid_sw.x, mid_sw.y)]))
        edges.append(GraphEdge(mid_sw.id, sw.id, [(mid_sw.x, mid_sw.y), (sw.x, sw.y)]))

    if add_cross:
        mid_x = (lx0 + lx1) / 2.0
        mid_y = (ly0 + ly1) / 2.0
        center = reg.add(mid_x, mid_y, NODE_INTERSECTION)
        n_mid  = reg.add(mid_x, ly1, NODE_INTERSECTION)
        s_mid  = reg.add(mid_x, ly0, NODE_INTERSECTION)
        e_mid  = reg.add(lx1,   mid_y, NODE_INTERSECTION)
        w_mid  = reg.add(lx0,   mid_y, NODE_INTERSECTION)
        edges += [
            GraphEdge(s_mid.id,  center.id, [(s_mid.x, s_mid.y),  (center.x, center.y)]),
            GraphEdge(center.id, n_mid.id,  [(center.x, center.y), (n_mid.x, n_mid.y)]),
            GraphEdge(w_mid.id,  center.id, [(w_mid.x, w_mid.y),  (center.x, center.y)]),
            GraphEdge(center.id, e_mid.id,  [(center.x, center.y), (e_mid.x, e_mid.y)]),
        ]

    g = ProposedGraph(
        nodes=reg.nodes, edges=edges,
        entry_points=[sw.id],
        generator_type="loop_custom",
        params={"offset_ft": offset_ft, "entry_side": entry_side, "add_cross": add_cross},
        parcel_area_sqft=area,
    )
    g.compute_metrics(area)
    return g


# ---------------------------------------------------------------------------
# 3. Grid generator  (NOVEL — not in production templates)
# ---------------------------------------------------------------------------

def generate_grid(
    bbox: BBox,
    parcel_area_sqft: float = 0.0,
    n_x: int = 3,
    n_y: int = 4,
    offset_ft: float = 40.0,
    entry_side: str = "south",
) -> ProposedGraph:
    """
    Regular N×M grid road network.

    Creates a grid of n_x vertical streets × n_y horizontal streets.
    This topology is NOT achievable with any of the four production templates.

    Args:
        n_x: number of N-S roads
        n_y: number of E-W roads
        offset_ft: inset from parcel boundary
    """
    minx, miny, maxx, maxy = bbox
    w = maxx - minx
    h = maxy - miny
    area = parcel_area_sqft or w * h

    gx0, gy0 = minx + offset_ft, miny + offset_ft
    gx1, gy1 = maxx - offset_ft, maxy - offset_ft
    gw = gx1 - gx0
    gh = gy1 - gy0

    if gw <= 0 or gh <= 0:
        offset_ft = min(w, h) * 0.08
        gx0, gy0 = minx + offset_ft, miny + offset_ft
        gx1, gy1 = maxx - offset_ft, maxy - offset_ft
        gw, gh = gx1 - gx0, gy1 - gy0

    nx = max(2, n_x)
    ny = max(2, n_y)

    xs = [gx0 + i * gw / (nx - 1) for i in range(nx)]
    ys = [gy0 + j * gh / (ny - 1) for j in range(ny)]

    reg = _NodeRegistry()
    node_grid = {}

    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            degree = (
                (i > 0) + (i < nx - 1) +  # horizontal connections
                (j > 0) + (j < ny - 1)     # vertical connections
            )
            ntype = NODE_INTERSECTION if degree >= 3 else NODE_DEAD_END
            n = reg.add(x, y, ntype)
            node_grid[(i, j)] = n

    edges = []
    # Horizontal edges
    for j in range(ny):
        for i in range(nx - 1):
            a, b = node_grid[(i, j)], node_grid[(i+1, j)]
            edges.append(GraphEdge(a.id, b.id, [(a.x, a.y), (b.x, b.y)]))
    # Vertical edges
    for i in range(nx):
        for j in range(ny - 1):
            a, b = node_grid[(i, j)], node_grid[(i, j+1)]
            edges.append(GraphEdge(a.id, b.id, [(a.x, a.y), (b.x, b.y)]))

    # Entry connector
    if entry_side in ("south", "north"):
        mid_i = nx // 2
        entry_node = node_grid[(mid_i, 0 if entry_side == "south" else ny - 1)]
        ext = reg.add(entry_node.x, miny if entry_side == "south" else maxy, NODE_ENTRY)
        edges.append(GraphEdge(ext.id, entry_node.id, [(ext.x, ext.y), (entry_node.x, entry_node.y)]))
    else:
        mid_j = ny // 2
        entry_node = node_grid[(0 if entry_side == "west" else nx - 1, mid_j)]
        ext = reg.add(minx if entry_side == "west" else maxx, entry_node.y, NODE_ENTRY)
        edges.append(GraphEdge(ext.id, entry_node.id, [(ext.x, ext.y), (entry_node.x, entry_node.y)]))

    g = ProposedGraph(
        nodes=reg.nodes, edges=edges,
        entry_points=[ext.id],
        generator_type="grid",
        params={"n_x": nx, "n_y": ny, "offset_ft": offset_ft, "entry_side": entry_side},
        parcel_area_sqft=area,
    )
    g.compute_metrics(area)
    return g


# ---------------------------------------------------------------------------
# 4. Herringbone generator  (NOVEL)
# ---------------------------------------------------------------------------

def generate_herringbone(
    bbox: BBox,
    parcel_area_sqft: float = 0.0,
    angle_deg: float = 45.0,
    spacing_ft: float = 150.0,
    entry_side: str = "south",
) -> ProposedGraph:
    """
    Herringbone / diagonal branch road network.

    Central spine + branches at ±angle_deg.
    Creates a distinctive V-shaped or arrow pattern not achievable
    with perpendicular-only templates.

    Args:
        angle_deg:   branch angle from the spine axis
        spacing_ft:  spacing between branch attachment points along spine
    """
    minx, miny, maxx, maxy = bbox
    w = maxx - minx
    h = maxy - miny
    area = parcel_area_sqft or w * h

    offset = min(w, h) * 0.08
    rad = math.radians(angle_deg)

    reg = _NodeRegistry()
    edges = []

    if entry_side in ("south", "north"):
        spine_x0 = (minx + maxx) / 2.0
        spine_y0 = miny + offset
        spine_y1 = maxy - offset

        entry = reg.add(spine_x0, miny if entry_side == "south" else maxy, NODE_ENTRY)
        spine_len = spine_y1 - spine_y0
        n_branches = max(2, int(spine_len / spacing_ft))
        step = spine_len / max(n_branches, 1)

        prev_spine = reg.add(spine_x0, spine_y0, NODE_INTERSECTION)
        edges.append(GraphEdge(entry.id, prev_spine.id, [(entry.x, entry.y), (prev_spine.x, prev_spine.y)]))

        for i in range(n_branches + 1):
            y = spine_y0 + i * step
            cur = reg.add(spine_x0, y, NODE_INTERSECTION if i < n_branches else NODE_DEAD_END)
            edges.append(GraphEdge(prev_spine.id, cur.id, [(prev_spine.x, prev_spine.y), (cur.x, cur.y)]))
            prev_spine = cur

            if i < n_branches:
                # Right branch
                blen = (w / 2.0 - offset) * 0.9
                bx_r = spine_x0 + blen * math.cos(rad)
                by_r = y          + blen * math.sin(rad)
                by_r = max(miny + offset, min(maxy - offset, by_r))
                rb = reg.add(bx_r, by_r, NODE_DEAD_END)
                edges.append(GraphEdge(cur.id, rb.id, [(cur.x, cur.y), (rb.x, rb.y)]))
                # Left branch (mirror)
                bx_l = spine_x0 - blen * math.cos(rad)
                lb = reg.add(bx_l, by_r, NODE_DEAD_END)
                edges.append(GraphEdge(cur.id, lb.id, [(cur.x, cur.y), (lb.x, lb.y)]))
    else:
        spine_y0 = (miny + maxy) / 2.0
        spine_x0 = minx + offset
        spine_x1 = maxx - offset

        entry = reg.add(minx if entry_side == "west" else maxx, spine_y0, NODE_ENTRY)
        spine_len = spine_x1 - spine_x0
        n_branches = max(2, int(spine_len / spacing_ft))
        step = spine_len / max(n_branches, 1)

        prev_spine = reg.add(spine_x0, spine_y0, NODE_INTERSECTION)
        edges.append(GraphEdge(entry.id, prev_spine.id, [(entry.x, entry.y), (prev_spine.x, prev_spine.y)]))

        for i in range(n_branches + 1):
            x = spine_x0 + i * step
            cur = reg.add(x, spine_y0, NODE_INTERSECTION if i < n_branches else NODE_DEAD_END)
            edges.append(GraphEdge(prev_spine.id, cur.id, [(prev_spine.x, prev_spine.y), (cur.x, cur.y)]))
            prev_spine = cur
            if i < n_branches:
                blen = (h / 2.0 - offset) * 0.9
                bx = x + blen * math.sin(rad)
                by_u = spine_y0 + blen * math.cos(rad)
                by_d = spine_y0 - blen * math.cos(rad)
                by_u = min(maxy - offset, by_u)
                by_d = max(miny + offset, by_d)
                ub = reg.add(bx, by_u, NODE_DEAD_END)
                db = reg.add(bx, by_d, NODE_DEAD_END)
                edges.append(GraphEdge(cur.id, ub.id, [(cur.x, cur.y), (ub.x, ub.y)]))
                edges.append(GraphEdge(cur.id, db.id, [(cur.x, cur.y), (db.x, db.y)]))

    g = ProposedGraph(
        nodes=reg.nodes, edges=edges,
        entry_points=[0],
        generator_type="herringbone",
        params={"angle_deg": angle_deg, "spacing_ft": spacing_ft, "entry_side": entry_side},
        parcel_area_sqft=area,
    )
    g.compute_metrics(area)
    return g


# ---------------------------------------------------------------------------
# 5. Radial generator  (NOVEL)
# ---------------------------------------------------------------------------

def generate_radial(
    bbox: BBox,
    parcel_area_sqft: float = 0.0,
    n_spokes: int = 4,
    n_rings: int = 2,
    entry_side: str = "south",
) -> ProposedGraph:
    """
    Hub-and-spoke radial road network.

    Central hub with roads radiating outward plus optional ring roads.
    Novel — not achievable with existing templates.

    Args:
        n_spokes: number of radial roads
        n_rings:  number of concentric ring roads (0 = pure radial)
    """
    minx, miny, maxx, maxy = bbox
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0
    r_max = min(maxx - minx, maxy - miny) / 2.0 * 0.85
    area = parcel_area_sqft or (maxx - minx) * (maxy - miny)

    reg = _NodeRegistry()
    edges = []

    hub = reg.add(cx, cy, NODE_INTERSECTION)

    # Radial spokes
    ring_nodes = [[] for _ in range(n_rings)]
    for s in range(n_spokes):
        angle = math.radians(s * 360.0 / n_spokes)
        prev = hub
        for r in range(1, n_rings + 2):
            frac = r / (n_rings + 1)
            rx = cx + r_max * frac * math.cos(angle)
            ry = cy + r_max * frac * math.sin(angle)
            ntype = NODE_INTERSECTION if r <= n_rings else NODE_DEAD_END
            cur = reg.add(rx, ry, ntype)
            edges.append(GraphEdge(prev.id, cur.id, [(prev.x, prev.y), (cur.x, cur.y)]))
            if r <= n_rings:
                ring_nodes[r - 1].append(cur)
            prev = cur

    # Ring roads connecting spokes at each radius
    for ring_idx, ring in enumerate(ring_nodes):
        if len(ring) >= 2:
            for i in range(len(ring)):
                a = ring[i]
                b = ring[(i + 1) % len(ring)]
                # Curved ring approximated as straight chord
                edges.append(GraphEdge(a.id, b.id, [(a.x, a.y), (b.x, b.y)]))

    # Entry connector
    entry_x = cx
    entry_y = miny
    if entry_side == "north":
        entry_y = maxy
    elif entry_side == "west":
        entry_x, entry_y = minx, cy
    elif entry_side == "east":
        entry_x, entry_y = maxx, cy
    ext = reg.add(entry_x, entry_y, NODE_ENTRY)
    edges.append(GraphEdge(ext.id, hub.id, [(ext.x, ext.y), (hub.x, hub.y)]))

    g = ProposedGraph(
        nodes=reg.nodes, edges=edges,
        entry_points=[ext.id],
        generator_type="radial",
        params={"n_spokes": n_spokes, "n_rings": n_rings, "entry_side": entry_side},
        parcel_area_sqft=area,
    )
    g.compute_metrics(area)
    return g


# ---------------------------------------------------------------------------
# 6. T-junction generator
# ---------------------------------------------------------------------------

def generate_t_junction(
    bbox: BBox,
    parcel_area_sqft: float = 0.0,
    offset_ft: float = 50.0,
    branch_spacing_ft: float = 150.0,
    entry_side: str = "south",
) -> ProposedGraph:
    """
    T-junction: two perpendicular spines meeting at a central junction.
    Cross between spine and parallel — more connectivity than pure spine.
    """
    minx, miny, maxx, maxy = bbox
    w = maxx - minx
    h = maxy - miny
    area = parcel_area_sqft or w * h

    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    reg = _NodeRegistry()
    edges = []

    # Entry + main spine
    if entry_side in ("south", "north"):
        ey = miny if entry_side == "south" else maxy
        entry = reg.add(cx, ey, NODE_ENTRY)
        jxn   = reg.add(cx, cy, NODE_INTERSECTION)
        spine_s = reg.add(cx, miny + offset_ft, NODE_DEAD_END)
        spine_n = reg.add(cx, maxy - offset_ft, NODE_DEAD_END)
        t_w = reg.add(minx + offset_ft, cy, NODE_DEAD_END)
        t_e = reg.add(maxx - offset_ft, cy, NODE_DEAD_END)
        edges += [
            GraphEdge(entry.id, spine_s.id, [(entry.x, entry.y), (spine_s.x, spine_s.y)]),
            GraphEdge(spine_s.id, jxn.id,   [(spine_s.x, spine_s.y), (jxn.x, jxn.y)]),
            GraphEdge(jxn.id, spine_n.id,   [(jxn.x, jxn.y), (spine_n.x, spine_n.y)]),
            GraphEdge(t_w.id, jxn.id,        [(t_w.x, t_w.y), (jxn.x, jxn.y)]),
            GraphEdge(jxn.id, t_e.id,        [(jxn.x, jxn.y), (t_e.x, t_e.y)]),
        ]
        # Branches off the cross arm
        n_branches = max(1, int((maxx - minx - 2 * offset_ft) / branch_spacing_ft))
        arm_len = (maxx - minx - 2 * offset_ft) / 2.0
        step = arm_len / max(n_branches, 1)
        for i in range(1, n_branches):
            for dx_sign in (-1.0, 1.0):
                bx = cx + dx_sign * i * step
                bn = reg.add(bx, maxy - offset_ft, NODE_DEAD_END)
                bs = reg.add(bx, miny + offset_ft, NODE_DEAD_END)
                bj = reg.add(bx, cy, NODE_INTERSECTION)
                edges += [
                    GraphEdge(bj.id, bn.id, [(bj.x, bj.y), (bn.x, bn.y)]),
                    GraphEdge(bj.id, bs.id, [(bj.x, bj.y), (bs.x, bs.y)]),
                ]
    g = ProposedGraph(
        nodes=reg.nodes, edges=edges,
        entry_points=[0],
        generator_type="t_junction",
        params={"offset_ft": offset_ft, "branch_spacing_ft": branch_spacing_ft,
                "entry_side": entry_side},
        parcel_area_sqft=area,
    )
    g.compute_metrics(area)
    return g


# ---------------------------------------------------------------------------
# Main generator function
# ---------------------------------------------------------------------------

GENERATOR_TYPES = ["spine", "loop_custom", "grid", "herringbone", "radial", "t_junction"]


def generate_graph_candidates(
    parcel_geojson: Optional[dict] = None,
    parcel_area_sqft: float = 0.0,
    n: int = 30,
    seed: int = 0,
    entry_sides: Optional[List[str]] = None,
    include_types: Optional[List[str]] = None,
) -> List[ProposedGraph]:
    """
    Generate n candidate road graph proposals for a parcel.

    Distributes candidates across all generator types with varied params.

    Args:
        parcel_geojson:    GeoJSON geometry (Polygon); if None uses square from area
        parcel_area_sqft:  parcel area for metrics
        n:                 total candidates to generate
        seed:              random seed
        entry_sides:       restrict entry sides to use (default: all four)
        include_types:     restrict generator types (default: all six)

    Returns:
        list of ProposedGraph
    """
    if parcel_geojson:
        bbox = _bbox_from_polygon(parcel_geojson)
    elif parcel_area_sqft > 0:
        bbox = _bbox_from_sqft(parcel_area_sqft)
    else:
        bbox = (0.0, 0.0, 660.0, 660.0)

    area = parcel_area_sqft or ((bbox[2]-bbox[0]) * (bbox[3]-bbox[1]))
    rng  = random.Random(seed)
    sides = entry_sides or ["south", "north", "east", "west"]
    types = include_types or GENERATOR_TYPES

    candidates: List[ProposedGraph] = []
    per_type = max(1, n // len(types))

    def _side() -> str:
        return rng.choice(sides)

    def _rand(lo: float, hi: float) -> float:
        return rng.uniform(lo, hi)

    # --- Spine variants ---
    if "spine" in types:
        for _ in range(per_type):
            candidates.append(generate_spine(
                bbox, area,
                offset_ft=_rand(30, 80),
                branch_spacing_ft=_rand(80, 200),
                branch_depth_fraction=_rand(0.3, 0.6),
                entry_side=_side(),
            ))

    # --- Loop variants ---
    if "loop_custom" in types:
        for i in range(per_type):
            candidates.append(generate_loop(
                bbox, area,
                offset_ft=_rand(40, 100),
                entry_side=_side(),
                add_cross=(i % 2 == 0),
            ))

    # --- Grid variants ---
    if "grid" in types:
        for _ in range(per_type):
            nx = rng.randint(2, 5)
            ny = rng.randint(2, 6)
            candidates.append(generate_grid(
                bbox, area,
                n_x=nx, n_y=ny,
                offset_ft=_rand(30, 70),
                entry_side=_side(),
            ))

    # --- Herringbone variants ---
    if "herringbone" in types:
        for _ in range(per_type):
            candidates.append(generate_herringbone(
                bbox, area,
                angle_deg=_rand(30, 70),
                spacing_ft=_rand(100, 200),
                entry_side=_side(),
            ))

    # --- Radial variants ---
    if "radial" in types:
        for _ in range(per_type):
            candidates.append(generate_radial(
                bbox, area,
                n_spokes=rng.randint(3, 8),
                n_rings=rng.randint(0, 2),
                entry_side=_side(),
            ))

    # --- T-junction variants ---
    if "t_junction" in types:
        for _ in range(per_type):
            candidates.append(generate_t_junction(
                bbox, area,
                offset_ft=_rand(40, 80),
                branch_spacing_ft=_rand(120, 250),
                entry_side=_side(),
            ))

    # Fill to n if needed
    while len(candidates) < n:
        gtype = rng.choice(types)
        if gtype == "grid":
            candidates.append(generate_grid(bbox, area,
                n_x=rng.randint(2, 4), n_y=rng.randint(2, 5),
                offset_ft=_rand(30, 70), entry_side=_side()))
        elif gtype == "herringbone":
            candidates.append(generate_herringbone(bbox, area,
                angle_deg=_rand(25, 75), spacing_ft=_rand(90, 220),
                entry_side=_side()))
        else:
            candidates.append(generate_spine(bbox, area,
                offset_ft=_rand(30, 80), branch_spacing_ft=_rand(80, 200),
                entry_side=_side()))

    return candidates[:n]
