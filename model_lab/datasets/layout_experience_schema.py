"""
Layout Experience Schema — model_lab Phase 10

Defines the canonical schema for production layout experiences used in
continuous learning. Experiences are serialized to JSONL and converted to
graph_training-compatible records for model retraining.

Production code is never imported here. All geometry is stored in local feet
(the same coordinate system used by the layout engine).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Experience record
# ---------------------------------------------------------------------------

@dataclass
class LayoutExperience:
    """
    A single production layout experience, ready for ingestion into model_lab.

    Geometry is stored in local feet (origin at parcel centroid), matching the
    coordinate system used by the production layout engine. This means parcel
    features computed from this geometry are directly comparable to synthetic
    training records.

    Fields
    ------
    parcel_id          : Stable ID (APN or UUID) for deduplication and tracking.
    parcel_geometry    : GeoJSON Polygon dict in local-feet coordinates.
    parcel_area_sqft   : Pre-computed parcel area (avoids re-projection errors).
    graph_nodes        : Serialized node list [{id, x, y, type}, ...].
    graph_edges        : Serialized edge list [{from_node, to_node, coords, length_ft}, ...].
    centerlines        : Fallback — raw polylines if graph_nodes/edges not available.
                         Each entry is [[x0,y0],[x1,y1],...] in local feet.
    lot_polygons       : Exterior rings of valid lots [[x,y],...] in local feet.
    layout_metrics     : Metrics dict from the subdivision result.
    layout_score       : Scalar score used for retraining target.
    generator_type     : Graph topology type (one of 6 canonical types).
    search_iterations  : Number of candidates evaluated to produce this result.
    timestamp          : ISO-8601 string of when the layout was generated.
    prior_used         : Whether the graph prior guided candidate selection.
    rank               : Rank of this layout among candidates (1 = best).
    source             : Provenance tag ("production" | "synthetic" | "imported").
    """

    # Required identity
    parcel_id:         str
    parcel_geometry:   Dict[str, Any]           # GeoJSON Polygon in local ft
    parcel_area_sqft:  float
    layout_score:      float
    generator_type:    str
    timestamp:         str

    # Graph topology (prefer graph_nodes+graph_edges; fall back to centerlines)
    graph_nodes:   List[Dict[str, Any]] = field(default_factory=list)
    graph_edges:   List[Dict[str, Any]] = field(default_factory=list)
    centerlines:   List[List[List[float]]] = field(default_factory=list)

    # Lot geometry
    lot_polygons:  List[List[List[float]]] = field(default_factory=list)

    # Subdivision metrics
    layout_metrics: Dict[str, Any] = field(default_factory=dict)

    # Search metadata
    search_iterations: int   = 0
    prior_used:        bool  = False
    rank:              int   = 1

    # Provenance
    source: str = "production"

    # -----------------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LayoutExperience":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    def validate(self) -> List[str]:
        """Return a list of validation errors (empty = valid)."""
        errors: List[str] = []
        if not self.parcel_id:
            errors.append("parcel_id is empty")
        if self.parcel_area_sqft <= 0:
            errors.append(f"parcel_area_sqft={self.parcel_area_sqft} must be > 0")
        if not (0.0 <= self.layout_score <= 3.0):
            errors.append(f"layout_score={self.layout_score} outside expected [0, 3]")
        if self.generator_type not in VALID_GENERATOR_TYPES:
            errors.append(f"unknown generator_type={self.generator_type!r}")
        has_graph = self.graph_nodes and self.graph_edges
        has_centerlines = bool(self.centerlines)
        if not has_graph and not has_centerlines:
            errors.append("must provide either (graph_nodes + graph_edges) or centerlines")
        if not self.parcel_geometry:
            errors.append("parcel_geometry is empty")
        elif self.parcel_geometry.get("type") not in ("Polygon", "MultiPolygon"):
            errors.append("parcel_geometry must be GeoJSON Polygon or MultiPolygon")
        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0


VALID_GENERATOR_TYPES = {
    "spine", "loop_custom", "grid", "herringbone", "radial", "t_junction",
}


# ---------------------------------------------------------------------------
# Production log record (raw API response + parcel context)
# ---------------------------------------------------------------------------

@dataclass
class ProductionLogRecord:
    """
    Raw production log record: API response enriched with parcel geometry.

    This is the format written by production logging middleware or a sidecar
    that intercepts POST /api/layout/generate requests/responses and saves them
    to a JSONL file for later import.

    Fields mirror the production API response schema augmented with the
    parcel local-feet geometry needed for feature extraction.
    """

    parcel_id:            str
    parcel_area_sqft:     float
    parcel_geometry_local_ft: Dict[str, Any]    # GeoJSON Polygon in local ft
    top_generator_type:   str
    top_score:            float
    top_lot_count:        int
    top_total_road_ft:    float
    top_total_lot_area_sqft: float
    top_dev_area_ratio:   float
    top_centerlines_local_ft: List[List[List[float]]]   # [[[x,y],...], ...]
    top_lot_polygons_local_ft: List[List[List[float]]]  # [exterior ring coords]
    top_rank:             int
    n_candidates:         int
    prior_used:           bool
    timestamp:            str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProductionLogRecord":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_layout_experience(self) -> LayoutExperience:
        metrics = {
            "lot_count":             self.top_lot_count,
            "total_road_ft":         self.top_total_road_ft,
            "total_lot_area_sqft":   self.top_total_lot_area_sqft,
            "dev_area_ratio":        self.top_dev_area_ratio,
        }
        return LayoutExperience(
            parcel_id=self.parcel_id,
            parcel_geometry=self.parcel_geometry_local_ft,
            parcel_area_sqft=self.parcel_area_sqft,
            layout_score=self.top_score,
            generator_type=self.top_generator_type,
            timestamp=self.timestamp,
            centerlines=self.top_centerlines_local_ft,
            lot_polygons=self.top_lot_polygons_local_ft,
            layout_metrics=metrics,
            search_iterations=self.n_candidates,
            prior_used=self.prior_used,
            rank=self.top_rank,
            source="production",
        )


# ---------------------------------------------------------------------------
# JSONL I/O helpers
# ---------------------------------------------------------------------------

def load_experiences(path: Path) -> List[LayoutExperience]:
    """Load all LayoutExperience records from a JSONL file."""
    experiences: List[LayoutExperience] = []
    path = Path(path)
    if not path.exists():
        return experiences
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                experiences.append(LayoutExperience.from_dict(d))
            except Exception as exc:
                print(f"  WARN: skipping line {lineno} in {path.name}: {exc}")
    return experiences


def save_experiences(
    experiences: List[LayoutExperience],
    path: Path,
    append: bool = False,
    deduplicate: bool = True,
) -> int:
    """
    Write experiences to a JSONL file.

    Args:
        experiences:  Records to write.
        path:         Output JSONL file path.
        append:       If True, append to existing; otherwise overwrite.
        deduplicate:  If True and appending, skip records already present
                      (matched by parcel_id + timestamp).

    Returns:
        Number of records actually written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_keys: set = set()
    if append and deduplicate and path.exists():
        existing = load_experiences(path)
        existing_keys = {(e.parcel_id, e.timestamp) for e in existing}

    mode = "a" if append else "w"
    written = 0
    with open(path, mode) as f:
        for exp in experiences:
            key = (exp.parcel_id, exp.timestamp)
            if deduplicate and key in existing_keys:
                continue
            f.write(exp.to_jsonl_line() + "\n")
            existing_keys.add(key)
            written += 1
    return written


def now_iso() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()
