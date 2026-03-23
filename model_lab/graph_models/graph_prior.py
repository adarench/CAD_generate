"""
Graph Prior Model — model_lab Phase 8

Loads the trained graph prior and scores ProposedGraph candidates
before any simulation, enabling guided graph generation.

Usage:
    prior = GraphPrior.load()
    scored = prior.rank_graphs(parcel_polygon, parcel_area_sqft, graphs)
    top = scored[:10]  # (score, graph) pairs, descending

No production code is modified.
"""

from __future__ import annotations

import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODEL_PATH = REPO_ROOT / "model_lab" / "models" / "graph_prior.pkl"


@dataclass
class GraphPriorPrediction:
    graph:          object    # ProposedGraph
    predicted_score: float
    rank:           int       # 1 = best


class GraphPrior:
    """Wrapper around the trained graph prior model."""

    def __init__(self, model, feature_names: List[str]):
        self._model        = model
        self._feature_names = feature_names

        # Split feature names into parcel vs graph buckets
        from model_lab.training.parcel_feature_extractor import PARCEL_FEATURE_NAMES
        from model_lab.training.graph_feature_extractor  import GRAPH_FEATURE_NAMES
        self._parcel_names = PARCEL_FEATURE_NAMES
        self._graph_names  = GRAPH_FEATURE_NAMES

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "GraphPrior":
        with open(path, "rb") as f:
            payload = pickle.load(f)
        return cls(payload["model"], payload["feature_names"])

    def _build_row(
        self,
        parcel_features: dict,
        graph_features:  dict,
    ) -> List[float]:
        row = [float(parcel_features.get(k, 0.0)) for k in self._parcel_names] + \
              [float(graph_features.get(k, 0.0))  for k in self._graph_names]
        return row

    def score_graph(
        self,
        graph,
        parcel_geojson: dict,
        parcel_area_sqft: float,
    ) -> float:
        """
        Predict layout score for a single graph.

        Args:
            graph:            ProposedGraph
            parcel_geojson:   GeoJSON polygon dict
            parcel_area_sqft: parcel area in sqft

        Returns:
            Predicted score (float).
        """
        from model_lab.training.parcel_feature_extractor import extract_parcel_features
        from model_lab.training.graph_feature_extractor  import extract_graph_features

        pf = extract_parcel_features(parcel_geojson, parcel_area_sqft)
        gf = extract_graph_features(graph, parcel_area_sqft)
        row = np.array([self._build_row(pf, gf)], dtype=np.float32)
        return float(self._model.predict(row)[0])

    def rank_graphs(
        self,
        graphs:           List,
        parcel_geojson:   dict,
        parcel_area_sqft: float,
    ) -> List[GraphPriorPrediction]:
        """
        Score and rank a list of ProposedGraphs.

        Returns:
            List of GraphPriorPrediction sorted by predicted_score descending.
        """
        from model_lab.training.parcel_feature_extractor import extract_parcel_features
        from model_lab.training.graph_feature_extractor  import extract_graph_features

        if not graphs:
            return []

        pf = extract_parcel_features(parcel_geojson, parcel_area_sqft)
        rows = []
        for g in graphs:
            gf = extract_graph_features(g, parcel_area_sqft)
            rows.append(self._build_row(pf, gf))

        X = np.array(rows, dtype=np.float32)
        preds = self._model.predict(X)

        paired = sorted(
            zip(preds, graphs),
            key=lambda x: x[0],
            reverse=True,
        )
        return [
            GraphPriorPrediction(graph=g, predicted_score=float(s), rank=i + 1)
            for i, (s, g) in enumerate(paired)
        ]


def generate_guided_graphs(
    parcel_geojson:   dict,
    parcel_area_sqft: float,
    n_final:          int = 12,
    n_pool:           int = 120,
    seed:             int = 0,
    prior:            Optional[GraphPrior] = None,
) -> List:
    """
    Generate n_final graph candidates guided by the prior model.

    Strategy — type-distribution reweighting:
      1. Generate a large pool of candidates (all types, uniform)
      2. Use the prior to compute the EXPECTED SCORE per generator type
      3. Allocate n_final slots proportionally to expected type scores
      4. Fill each slot by sampling randomly (not greedily) from that type

    This keeps high-variance individual candidates in play while steering
    the type distribution toward topologies the prior thinks are promising.
    The prior guides *how many* of each type to include, not *which specific*
    graph within a type — preserving the within-type diversity that evolution
    needs to find winners.

    Args:
        parcel_geojson:   GeoJSON polygon dict
        parcel_area_sqft: parcel area in sqft
        n_final:          number of candidates to return
        n_pool:           pool size to generate before type-reweighting
        seed:             random seed
        prior:            pre-loaded GraphPrior (loaded if None)

    Returns:
        List of up to n_final ProposedGraph objects (type-reweighted).
    """
    from model_lab.graph_models.graph_generator import generate_graph_candidates
    from collections import defaultdict
    import random as _random

    if prior is None:
        prior = GraphPrior.load()

    pool = generate_graph_candidates(
        parcel_geojson=parcel_geojson,
        parcel_area_sqft=parcel_area_sqft,
        n=n_pool,
        seed=seed,
    )

    if not pool:
        return []

    # Score the pool with the prior
    ranked = prior.rank_graphs(pool, parcel_geojson, parcel_area_sqft)

    # Compute mean predicted score per generator type
    by_type: dict = defaultdict(list)
    for p in ranked:
        by_type[p.graph.generator_type].append(p)

    type_mean_score = {}
    for gt, preds in by_type.items():
        type_mean_score[gt] = sum(p.predicted_score for p in preds) / len(preds)

    # Softmax-weighted allocation across types
    import math as _math
    temperature = 0.5   # lower = more exploitative; higher = more uniform
    types = list(type_mean_score.keys())
    raw_weights = [_math.exp(type_mean_score[t] / temperature) for t in types]
    total_w = sum(raw_weights)
    type_weights = {t: w / total_w for t, w in zip(types, raw_weights)}

    # Allocate n_final slots, minimum 1 per type (ensures diversity)
    n_types = len(types)
    min_per_type = 1
    remaining = n_final - min_per_type * n_types
    allocations = {t: min_per_type for t in types}
    if remaining > 0:
        for t in sorted(types, key=lambda x: type_weights[x], reverse=True):
            extra = max(0, int(type_weights[t] * n_final))
            add = min(extra, remaining)
            allocations[t] += add
            remaining -= add
            if remaining <= 0:
                break
        # Any leftover goes to the top type
        if remaining > 0:
            top_type = max(types, key=lambda x: type_weights[x])
            allocations[top_type] += remaining

    # Sample from each type (random, not greedy — preserves within-type variance)
    rng = _random.Random(seed + 99)
    selected = []
    for gt in types:
        type_graphs = [p.graph for p in by_type[gt]]
        n_take = min(allocations[gt], len(type_graphs))
        chosen = rng.sample(type_graphs, n_take)
        selected.extend(chosen)

    return selected[:n_final]
