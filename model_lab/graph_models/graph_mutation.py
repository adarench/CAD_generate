"""
Graph Mutation Operations — model_lab

Evolutionary mutation operators for ProposedGraph objects.

Operations
----------
add_branch         — grow a new dead-end from any non-dead-end node
remove_branch      — prune a dead-end branch
shift_node         — perturb an intersection position
adjust_branch_angle — rotate a branch around its attachment point
extend_road        — lengthen a dead-end edge
shorten_road       — shorten a dead-end edge (toward minimum)
split_edge         — insert a new intersection in the middle of an edge
mutate_graph       — apply a random mix of the above

No production code is modified.
"""

from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import List, Optional, Tuple

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
# Helpers
# ---------------------------------------------------------------------------

def _copy(g: ProposedGraph) -> ProposedGraph:
    """Deep copy a graph for mutation."""
    return deepcopy(g)


def _next_id(g: ProposedGraph) -> int:
    return max((n.id for n in g.nodes), default=-1) + 1


def _set_type(g: ProposedGraph, nid: int, ntype: str) -> None:
    for n in g.nodes:
        if n.id == nid:
            n.type = ntype
            return


def _node_degree(g: ProposedGraph, nid: int) -> int:
    return sum(1 for e in g.edges if e.from_node == nid or e.to_node == nid)


def _dead_end_edges(g: ProposedGraph) -> List[GraphEdge]:
    """Edges where one endpoint is a dead-end."""
    dead_ids = {n.id for n in g.nodes if n.type in (NODE_DEAD_END, NODE_TERMINUS)}
    return [e for e in g.edges if e.from_node in dead_ids or e.to_node in dead_ids]


def _junction_nodes(g: ProposedGraph) -> List[GraphNode]:
    return [n for n in g.nodes if n.type in (NODE_INTERSECTION, NODE_ENTRY)]


def _bbox_of_graph(g: ProposedGraph) -> Tuple[float, float, float, float]:
    if not g.nodes:
        return (0.0, 0.0, 100.0, 100.0)
    xs = [n.x for n in g.nodes]
    ys = [n.y for n in g.nodes]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Mutation operations
# ---------------------------------------------------------------------------

def add_branch(
    g: ProposedGraph,
    rng: random.Random,
    min_length: float = 60.0,
    max_length: float = 200.0,
) -> ProposedGraph:
    """
    Grow a new dead-end branch from a random junction node.

    The new branch extends in a direction not already covered by existing edges,
    at a length drawn from [min_length, max_length].
    """
    g = _copy(g)
    junctions = _junction_nodes(g)
    if not junctions:
        return g

    src = rng.choice(junctions)
    # Pick angle not too close to existing edges from src
    existing_angles = set()
    for e in g.edges:
        if e.from_node == src.id and len(e.coords) >= 2:
            dx = e.coords[1][0] - e.coords[0][0]
            dy = e.coords[1][1] - e.coords[0][1]
            existing_angles.add(math.degrees(math.atan2(dy, dx)) % 360)
        elif e.to_node == src.id and len(e.coords) >= 2:
            dx = e.coords[-2][0] - e.coords[-1][0]
            dy = e.coords[-2][1] - e.coords[-1][1]
            existing_angles.add(math.degrees(math.atan2(dy, dx)) % 360)

    for _ in range(20):
        angle_deg = rng.uniform(0, 360)
        if all(abs((angle_deg - a) % 360) > 20 for a in existing_angles):
            break

    length = rng.uniform(min_length, max_length)
    rad = math.radians(angle_deg)
    nid = _next_id(g)
    new_x = src.x + length * math.cos(rad)
    new_y = src.y + length * math.sin(rad)
    new_node = GraphNode(id=nid, x=new_x, y=new_y, type=NODE_DEAD_END)
    g.nodes.append(new_node)
    g.edges.append(GraphEdge(src.id, nid, [(src.x, src.y), (new_x, new_y)]))

    # Upgrade src to intersection if it was a dead-end
    if src.type in (NODE_DEAD_END, NODE_TERMINUS):
        _set_type(g, src.id, NODE_INTERSECTION)

    g.compute_metrics(g.parcel_area_sqft)
    return g


def remove_branch(g: ProposedGraph, rng: random.Random) -> ProposedGraph:
    """
    Prune a random dead-end branch edge.

    If the source becomes a dead-end (degree=1) it's reclassified.
    Does not remove entry nodes.
    """
    g = _copy(g)
    dead_edges = _dead_end_edges(g)
    if not dead_edges:
        return g

    edge = rng.choice(dead_edges)
    dead_ids = {n.id for n in g.nodes if n.type in (NODE_DEAD_END, NODE_TERMINUS)}

    # Identify which endpoint is dead-end
    if edge.from_node in dead_ids:
        remove_nid = edge.from_node
        parent_nid = edge.to_node
    else:
        remove_nid = edge.to_node
        parent_nid = edge.from_node

    # Don't remove entry points
    entry_ids = {n.id for n in g.nodes if n.type == NODE_ENTRY}
    if remove_nid in entry_ids:
        return g

    g.nodes = [n for n in g.nodes if n.id != remove_nid]
    g.edges = [e for e in g.edges if e != edge]

    # Downgrade parent if it's now degree-1
    if _node_degree(g, parent_nid) == 1:
        _set_type(g, parent_nid, NODE_DEAD_END)

    g.compute_metrics(g.parcel_area_sqft)
    return g


def shift_node(
    g: ProposedGraph,
    rng: random.Random,
    magnitude: float = 30.0,
) -> ProposedGraph:
    """
    Perturb an intersection node position by up to magnitude feet.
    Updates all edges connected to this node.
    """
    g = _copy(g)
    junctions = [n for n in g.nodes if n.type == NODE_INTERSECTION]
    if not junctions:
        return g

    n = rng.choice(junctions)
    dx = rng.gauss(0, magnitude / 2)
    dy = rng.gauss(0, magnitude / 2)
    old_x, old_y = n.x, n.y
    n.x += dx
    n.y += dy

    # Update edge coords
    for edge in g.edges:
        coords = list(edge.coords)
        if edge.from_node == n.id:
            coords[0] = (n.x, n.y)
        if edge.to_node == n.id:
            coords[-1] = (n.x, n.y)
        # Rebuild edge (frozen-like — reassign)
        object.__setattr__(edge, 'coords', coords)
        # Recompute length
        total = 0.0
        for i in range(len(coords) - 1):
            ddx = coords[i+1][0] - coords[i][0]
            ddy = coords[i+1][1] - coords[i][1]
            total += math.sqrt(ddx*ddx + ddy*ddy)
        object.__setattr__(edge, 'length_ft', total)

    g.compute_metrics(g.parcel_area_sqft)
    return g


def adjust_branch_angle(
    g: ProposedGraph,
    rng: random.Random,
    max_delta_deg: float = 20.0,
) -> ProposedGraph:
    """
    Rotate a dead-end branch around its attachment point by ±max_delta_deg.
    """
    g = _copy(g)
    dead_edges = _dead_end_edges(g)
    if not dead_edges:
        return g

    edge = rng.choice(dead_edges)
    dead_ids = {n.id for n in g.nodes if n.type in (NODE_DEAD_END, NODE_TERMINUS)}

    if edge.to_node in dead_ids:
        tip_nid = edge.to_node
        base_nid = edge.from_node
    else:
        tip_nid = edge.from_node
        base_nid = edge.to_node

    tip  = g.node_by_id(tip_nid)
    base = g.node_by_id(base_nid)
    if not tip or not base:
        return g

    dx = tip.x - base.x
    dy = tip.y - base.y
    length = math.sqrt(dx*dx + dy*dy) or 1.0
    current_angle = math.atan2(dy, dx)
    delta = math.radians(rng.uniform(-max_delta_deg, max_delta_deg))
    new_angle = current_angle + delta

    tip.x = base.x + length * math.cos(new_angle)
    tip.y = base.y + length * math.sin(new_angle)

    # Update edge coords
    coords = [(base.x, base.y), (tip.x, tip.y)]
    if edge.from_node == base_nid:
        object.__setattr__(edge, 'coords', coords)
    else:
        object.__setattr__(edge, 'coords', list(reversed(coords)))

    g.compute_metrics(g.parcel_area_sqft)
    return g


def extend_road(
    g: ProposedGraph,
    rng: random.Random,
    delta_ft: Optional[float] = None,
) -> ProposedGraph:
    """Extend a dead-end edge by delta_ft (default: 10–50% of its current length)."""
    g = _copy(g)
    dead_edges = _dead_end_edges(g)
    if not dead_edges:
        return g

    edge = rng.choice(dead_edges)
    dead_ids = {n.id for n in g.nodes if n.type in (NODE_DEAD_END, NODE_TERMINUS)}
    tip_nid  = edge.to_node if edge.to_node in dead_ids else edge.from_node
    base_nid = edge.from_node if tip_nid == edge.to_node else edge.to_node

    tip  = g.node_by_id(tip_nid)
    base = g.node_by_id(base_nid)
    if not tip or not base:
        return g

    dx = tip.x - base.x
    dy = tip.y - base.y
    length = math.sqrt(dx*dx + dy*dy) or 1.0
    ext = delta_ft or rng.uniform(length * 0.1, length * 0.5)
    scale = (length + ext) / length
    tip.x = base.x + dx * scale
    tip.y = base.y + dy * scale

    coords = [(base.x, base.y), (tip.x, tip.y)]
    if edge.from_node == base_nid:
        object.__setattr__(edge, 'coords', coords)
    else:
        object.__setattr__(edge, 'coords', list(reversed(coords)))
    object.__setattr__(edge, 'length_ft', length + ext)

    g.compute_metrics(g.parcel_area_sqft)
    return g


def shorten_road(
    g: ProposedGraph,
    rng: random.Random,
    min_length: float = 40.0,
) -> ProposedGraph:
    """Shorten a dead-end edge, preserving minimum length."""
    g = _copy(g)
    dead_edges = [e for e in _dead_end_edges(g) if e.length_ft > min_length * 1.5]
    if not dead_edges:
        return g

    edge = rng.choice(dead_edges)
    dead_ids = {n.id for n in g.nodes if n.type in (NODE_DEAD_END, NODE_TERMINUS)}
    tip_nid  = edge.to_node if edge.to_node in dead_ids else edge.from_node
    base_nid = edge.from_node if tip_nid == edge.to_node else edge.to_node

    tip  = g.node_by_id(tip_nid)
    base = g.node_by_id(base_nid)
    if not tip or not base:
        return g

    dx = tip.x - base.x
    dy = tip.y - base.y
    length = math.sqrt(dx*dx + dy*dy) or 1.0
    reduction = rng.uniform(0.1, 0.4) * length
    new_len = max(min_length, length - reduction)
    scale = new_len / length

    tip.x = base.x + dx * scale
    tip.y = base.y + dy * scale
    coords = [(base.x, base.y), (tip.x, tip.y)]
    if edge.from_node == base_nid:
        object.__setattr__(edge, 'coords', coords)
    else:
        object.__setattr__(edge, 'coords', list(reversed(coords)))
    object.__setattr__(edge, 'length_ft', new_len)

    g.compute_metrics(g.parcel_area_sqft)
    return g


def split_edge(g: ProposedGraph, rng: random.Random) -> ProposedGraph:
    """
    Insert a new intersection node in the middle of a random edge.
    This creates two new edges and enables new branches at the midpoint.
    """
    g = _copy(g)
    if not g.edges:
        return g

    edge = rng.choice(g.edges)
    coords = edge.coords
    mid_idx = len(coords) // 2
    mx = (coords[0][0] + coords[-1][0]) / 2.0
    my = (coords[0][1] + coords[-1][1]) / 2.0

    new_nid = _next_id(g)
    new_node = GraphNode(id=new_nid, x=mx, y=my, type=NODE_INTERSECTION)
    g.nodes.append(new_node)

    g.edges.remove(edge)
    c1 = [(coords[0][0], coords[0][1]), (mx, my)]
    c2 = [(mx, my), (coords[-1][0], coords[-1][1])]
    g.edges.append(GraphEdge(edge.from_node, new_nid, c1))
    g.edges.append(GraphEdge(new_nid, edge.to_node, c2))

    # Reclassify endpoints
    _set_type(g, edge.from_node, NODE_INTERSECTION)
    _set_type(g, edge.to_node,   NODE_INTERSECTION)

    g.compute_metrics(g.parcel_area_sqft)
    return g


# ---------------------------------------------------------------------------
# High-level mutation
# ---------------------------------------------------------------------------

OPERATIONS = [
    ("add_branch",          0.30),
    ("remove_branch",       0.15),
    ("shift_node",          0.20),
    ("adjust_branch_angle", 0.15),
    ("extend_road",         0.10),
    ("shorten_road",        0.05),
    ("split_edge",          0.05),
]


def mutate_graph(
    g: ProposedGraph,
    seed: Optional[int] = None,
    n_ops: int = 2,
    magnitude: float = 30.0,
) -> ProposedGraph:
    """
    Apply n_ops random mutation operations to the graph.

    Args:
        g:         source graph (not modified — returns a new copy)
        seed:      random seed
        n_ops:     number of operations to apply
        magnitude: perturbation magnitude in feet
    """
    rng = random.Random(seed)
    ops, weights = zip(*OPERATIONS)
    result = g
    for _ in range(n_ops):
        op = rng.choices(list(ops), weights=list(weights), k=1)[0]
        if op == "add_branch":
            result = add_branch(result, rng, max_length=magnitude * 4)
        elif op == "remove_branch":
            result = remove_branch(result, rng)
        elif op == "shift_node":
            result = shift_node(result, rng, magnitude=magnitude)
        elif op == "adjust_branch_angle":
            result = adjust_branch_angle(result, rng)
        elif op == "extend_road":
            result = extend_road(result, rng)
        elif op == "shorten_road":
            result = shorten_road(result, rng)
        elif op == "split_edge":
            result = split_edge(result, rng)

    return result


def mutate_population(
    graphs: List[ProposedGraph],
    n_offspring: int,
    magnitude: float = 30.0,
    n_ops: int = 2,
    base_seed: int = 0,
) -> List[ProposedGraph]:
    """Mutate a list of graphs to produce n_offspring."""
    if not graphs:
        return []
    per_parent = max(1, n_offspring // len(graphs))
    extra = n_offspring - per_parent * len(graphs)
    offspring = []
    for i, g in enumerate(graphs):
        count = per_parent + (1 if i < extra else 0)
        for j in range(count):
            child = mutate_graph(g, seed=base_seed + i * 1000 + j,
                                 n_ops=n_ops, magnitude=magnitude)
            offspring.append(child)
    return offspring[:n_offspring]
