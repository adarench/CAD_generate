"""
Production Layout Log Importer — model_lab Phase 10

Ingests layout outputs from production and converts them into
graph_training-compatible records for model retraining.

Accepts two input formats:
  1. "experience" — pre-formatted LayoutExperience JSONL files
  2. "production_log" — raw ProductionLogRecord JSONL (API response + parcel context)

Output appended to:
    model_lab/datasets/layout_experience.jsonl

Usage:
    python -m model_lab.training.import_layout_logs \\
        --input /path/to/production_log.jsonl \\
        [--format experience|production_log] \\
        [--output model_lab/datasets/layout_experience.jsonl] \\
        [--verbose]

No production code is imported. All geometry must be in local feet.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.datasets.layout_experience_schema import (
    VALID_GENERATOR_TYPES,
    LayoutExperience,
    ProductionLogRecord,
    load_experiences,
    now_iso,
    save_experiences,
)
from model_lab.training.parcel_feature_extractor import (
    PARCEL_FEATURE_NAMES,
    extract_parcel_features,
)
from model_lab.training.graph_feature_extractor import (
    GRAPH_FEATURE_NAMES,
    extract_graph_features,
)
from model_lab.graph_models.road_graph import (
    GraphEdge,
    GraphNode,
    ProposedGraph,
    ProposedGraphMetrics,
    NODE_DEAD_END,
    NODE_ENTRY,
    NODE_INTERSECTION,
    NODE_TERMINUS,
)

DEFAULT_OUTPUT = REPO_ROOT / "model_lab" / "datasets" / "layout_experience.jsonl"


# ---------------------------------------------------------------------------
# Centerlines → ProposedGraph reconstruction
# ---------------------------------------------------------------------------

def _snap(v: float, snap: float = 0.5) -> float:
    return round(v / snap) * snap


def centerlines_to_proposed_graph(
    centerlines: List[List[List[float]]],
    generator_type: str,
    parcel_area_sqft: float = 0.0,
) -> ProposedGraph:
    """
    Build a minimal ProposedGraph from a list of polyline coordinate lists.

    Each centerline is [[x0,y0],[x1,y1],...] in local feet.
    Endpoints are snapped to a 0.5ft grid to merge near-coincident nodes.

    This enables graph_feature_extractor to work on production road outputs
    without requiring the original ProposedGraph object.
    """
    node_map: Dict[Tuple[float, float], int] = {}
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    entry_points: List[int] = []

    def _get_node(x: float, y: float) -> int:
        key = (_snap(x), _snap(y))
        if key not in node_map:
            nid = len(nodes)
            node_map[key] = nid
            nodes.append(GraphNode(id=nid, x=key[0], y=key[1], type=NODE_TERMINUS))
        return node_map[key]

    for line in centerlines:
        if len(line) < 2:
            continue
        seg_coords = [[float(x), float(y)] for x, y in line]
        for i in range(len(seg_coords) - 1):
            u = _get_node(*seg_coords[i])
            v = _get_node(*seg_coords[i + 1])
            if u == v:
                continue
            edge_coords = [seg_coords[i], seg_coords[i + 1]]
            edges.append(GraphEdge(from_node=u, to_node=v, coords=edge_coords))

    if not nodes:
        # Degenerate — return empty graph
        return ProposedGraph(
            generator_type=generator_type,
            parcel_area_sqft=parcel_area_sqft,
        )

    # Compute node degrees and classify
    degree: Dict[int, int] = {}
    for e in edges:
        degree[e.from_node] = degree.get(e.from_node, 0) + 1
        degree[e.to_node]   = degree.get(e.to_node, 0) + 1

    for node in nodes:
        d = degree.get(node.id, 0)
        if d >= 3:
            node.type = NODE_INTERSECTION
        elif d == 1:
            node.type = NODE_DEAD_END
        else:
            node.type = NODE_TERMINUS

    # Compute metrics
    n_nodes        = len(nodes)
    n_edges        = len(edges)
    n_intersect    = sum(1 for d in degree.values() if d >= 3)
    n_dead_ends    = sum(1 for d in degree.values() if d == 1)
    total_road_ft  = sum(e.length_ft for e in edges)
    avg_edge_ft    = total_road_ft / max(n_edges, 1)
    density        = total_road_ft / max(parcel_area_sqft / 43560.0, 0.01)

    metrics = ProposedGraphMetrics(
        node_count=n_nodes,
        edge_count=n_edges,
        intersection_count=n_intersect,
        dead_end_count=n_dead_ends,
        entry_count=n_dead_ends,    # dead-ends approximate entries
        total_road_length_ft=total_road_ft,
        avg_edge_length_ft=avg_edge_ft,
        road_density_ft_per_acre=density,
        topology_class=generator_type,
    )

    graph = ProposedGraph(
        nodes=nodes,
        edges=edges,
        entry_points=entry_points,
        metrics=metrics,
        generator_type=generator_type,
        parcel_area_sqft=parcel_area_sqft,
    )
    return graph


def graph_nodes_edges_to_proposed_graph(
    nodes_data: List[Dict],
    edges_data: List[Dict],
    generator_type: str,
    parcel_area_sqft: float = 0.0,
) -> ProposedGraph:
    """Reconstruct ProposedGraph from serialized nodes/edges dicts."""
    nodes = [
        GraphNode(
            id=d["id"],
            x=float(d["x"]),
            y=float(d["y"]),
            type=d.get("type", NODE_TERMINUS),
        )
        for d in nodes_data
    ]
    edges = [
        GraphEdge(
            from_node=int(d["from_node"]),
            to_node=int(d["to_node"]),
            coords=[[float(c[0]), float(c[1])] for c in d.get("coords", [])],
        )
        for d in edges_data
        if len(d.get("coords", [])) >= 2
    ]

    degree: Dict[int, int] = {}
    for e in edges:
        degree[e.from_node] = degree.get(e.from_node, 0) + 1
        degree[e.to_node]   = degree.get(e.to_node, 0) + 1

    n_intersect   = sum(1 for d in degree.values() if d >= 3)
    n_dead_ends   = sum(1 for d in degree.values() if d == 1)
    total_road_ft = sum(e.length_ft for e in edges)
    avg_edge_ft   = total_road_ft / max(len(edges), 1)
    density       = total_road_ft / max(parcel_area_sqft / 43560.0, 0.01)

    metrics = ProposedGraphMetrics(
        node_count=len(nodes),
        edge_count=len(edges),
        intersection_count=n_intersect,
        dead_end_count=n_dead_ends,
        entry_count=n_dead_ends,
        total_road_length_ft=total_road_ft,
        avg_edge_length_ft=avg_edge_ft,
        road_density_ft_per_acre=density,
        topology_class=generator_type,
    )

    return ProposedGraph(
        nodes=nodes,
        edges=edges,
        entry_points=[],
        metrics=metrics,
        generator_type=generator_type,
        parcel_area_sqft=parcel_area_sqft,
    )


# ---------------------------------------------------------------------------
# ML score re-computation (using model_lab scoring formula)
# ---------------------------------------------------------------------------

def _compute_modellab_score(metrics: Dict[str, Any]) -> Optional[float]:
    """
    Re-compute layout score using model_lab's canonical formula:
        score = 0.6 * (lot_count/40) + 0.4 * (dev_area / road_len / 200)

    This normalises production scores (which use a different formula)
    onto the same scale as synthetic training records.

    Returns None if required metrics are missing.
    """
    lot_count  = metrics.get("lot_count") or metrics.get("generated_lot_count")
    road_len   = metrics.get("total_road_ft") or metrics.get("road_length_ft")
    dev_area   = metrics.get("total_lot_area_sqft") or metrics.get("developable_area_sqft")

    if lot_count is None or road_len is None or dev_area is None:
        return None

    lot_count = float(lot_count)
    road_len  = float(road_len)
    dev_area  = float(dev_area)

    if road_len <= 0:
        return None

    yield_sc  = lot_count / 40.0
    eff_sc    = (dev_area / road_len) / 200.0
    return 0.6 * yield_sc + 0.4 * eff_sc


# ---------------------------------------------------------------------------
# Experience → training record conversion
# ---------------------------------------------------------------------------

def experience_to_training_record(
    exp: LayoutExperience,
) -> Optional[Dict[str, Any]]:
    """
    Convert a LayoutExperience to a graph_training.jsonl-compatible record.

    Pipeline:
      1. Reconstruct ProposedGraph from nodes/edges or centerlines
      2. Extract parcel features (24) from local-ft GeoJSON polygon
      3. Extract graph features (32) from reconstructed graph
      4. Re-compute score using model_lab formula (if metrics available)
      5. Return merged record dict

    Returns None if conversion fails.
    """
    if not exp.is_valid():
        return None

    # 1. Rebuild graph
    if exp.graph_nodes and exp.graph_edges:
        graph = graph_nodes_edges_to_proposed_graph(
            exp.graph_nodes, exp.graph_edges,
            exp.generator_type, exp.parcel_area_sqft,
        )
    elif exp.centerlines:
        graph = centerlines_to_proposed_graph(
            exp.centerlines, exp.generator_type, exp.parcel_area_sqft,
        )
    else:
        return None

    if not graph.edges:
        return None

    # 2. Parcel features
    try:
        pf = extract_parcel_features(exp.parcel_geometry, exp.parcel_area_sqft)
    except Exception as exc:
        return None

    # 3. Graph features
    try:
        gf = extract_graph_features(graph, exp.parcel_area_sqft)
    except Exception as exc:
        return None

    # 4. Score — prefer re-computed model_lab score, fall back to stored
    score = _compute_modellab_score(exp.layout_metrics)
    if score is None:
        score = exp.layout_score

    # 5. Assemble record
    lot_count   = exp.layout_metrics.get("lot_count", 0)
    road_length = exp.layout_metrics.get("total_road_ft", 0.0)

    return {
        "parcel_id":       f"{exp.parcel_id}_prod",
        "parcel_features": pf,
        "graph_features":  gf,
        "generator_type":  exp.generator_type,
        "score":           float(score),
        "lot_count":       int(lot_count),
        "road_length_ft":  float(road_length),
        "source":          exp.source,
        "timestamp":       exp.timestamp,
    }


# ---------------------------------------------------------------------------
# Import pipeline
# ---------------------------------------------------------------------------

def import_experiences(
    experiences: List[LayoutExperience],
    output_path: Path = DEFAULT_OUTPUT,
    verbose: bool = True,
) -> Dict[str, int]:
    """
    Convert a list of LayoutExperience objects to training records and
    append them to `output_path` (graph_training-compatible JSONL).

    Returns stats dict with keys: total, valid, converted, skipped, written.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {"total": 0, "valid": 0, "converted": 0, "skipped": 0, "written": 0}

    # Load existing records for deduplication
    existing_keys: set = set()
    if output_path.exists():
        with open(output_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        d = json.loads(line)
                        key = (d.get("parcel_id", ""), d.get("timestamp", ""))
                        existing_keys.add(key)
                    except Exception:
                        pass

    new_records: List[Dict] = []
    for exp in experiences:
        stats["total"] += 1
        errors = exp.validate()
        if errors:
            if verbose:
                print(f"  SKIP {exp.parcel_id}: {errors[0]}")
            stats["skipped"] += 1
            continue

        stats["valid"] += 1
        rec = experience_to_training_record(exp)
        if rec is None:
            if verbose:
                print(f"  SKIP {exp.parcel_id}: feature extraction failed")
            stats["skipped"] += 1
            continue

        key = (rec["parcel_id"], rec.get("timestamp", ""))
        if key in existing_keys:
            stats["skipped"] += 1
            continue

        new_records.append(rec)
        existing_keys.add(key)
        stats["converted"] += 1

    # Append new records
    with open(output_path, "a") as f:
        for rec in new_records:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
            stats["written"] += 1

    if verbose:
        print(f"  Imported: {stats['written']} new records → {output_path.name}")
        print(f"  (total={stats['total']}  valid={stats['valid']}  "
              f"skipped={stats['skipped']})")

    return stats


def import_from_file(
    input_path: Path,
    output_path: Path = DEFAULT_OUTPUT,
    fmt: str = "experience",
    verbose: bool = True,
) -> Dict[str, int]:
    """
    Import layout experiences from a JSONL file.

    Args:
        input_path:  Path to input JSONL file.
        output_path: Path to output training JSONL file.
        fmt:         Input format: "experience" or "production_log".
        verbose:     Print progress.

    Returns:
        Stats dict.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if verbose:
        print(f"[import] Reading {input_path.name}  format={fmt}")

    experiences: List[LayoutExperience] = []
    errors = 0

    with open(input_path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if fmt == "experience":
                    experiences.append(LayoutExperience.from_dict(d))
                elif fmt == "production_log":
                    log = ProductionLogRecord.from_dict(d)
                    experiences.append(log.to_layout_experience())
                else:
                    raise ValueError(f"Unknown format: {fmt!r}")
            except Exception as exc:
                if verbose:
                    print(f"  WARN line {lineno}: {exc}")
                errors += 1

    if verbose and errors:
        print(f"  {errors} lines failed to parse")

    return import_experiences(experiences, output_path, verbose)


def import_from_directory(
    input_dir: Path,
    output_path: Path = DEFAULT_OUTPUT,
    fmt: str = "experience",
    pattern: str = "*.jsonl",
    verbose: bool = True,
) -> Dict[str, int]:
    """
    Import all matching JSONL files from a directory.

    Returns aggregate stats.
    """
    input_dir = Path(input_dir)
    files = sorted(input_dir.glob(pattern))
    if not files:
        if verbose:
            print(f"[import] No files matching {pattern} in {input_dir}")
        return {"total": 0, "valid": 0, "converted": 0, "skipped": 0, "written": 0}

    totals = {"total": 0, "valid": 0, "converted": 0, "skipped": 0, "written": 0}
    for f in files:
        stats = import_from_file(f, output_path, fmt, verbose)
        for k in totals:
            totals[k] += stats.get(k, 0)

    if verbose:
        print(f"\n[import] Total across {len(files)} files: {totals['written']} records written")
    return totals


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import production layout logs into model_lab training dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input",   required=True, help="Input JSONL file or directory")
    parser.add_argument("--output",  default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--format",  default="experience",
                        choices=["experience", "production_log"],
                        help="Input record format")
    parser.add_argument("--pattern", default="*.jsonl", help="Glob for directory mode")
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    input_path  = Path(args.input)
    output_path = Path(args.output)

    if input_path.is_dir():
        stats = import_from_directory(input_path, output_path, args.format,
                                       args.pattern, args.verbose)
    else:
        stats = import_from_file(input_path, output_path, args.format, args.verbose)

    print("\nDone.", stats)
