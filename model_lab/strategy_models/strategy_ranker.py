"""
Strategy Ranker — model_lab

Inference module for the trained layout score predictor.

Loads a saved model and exposes a clean interface for:
  - Predicting score for a single (parcel, strategy) pair
  - Ranking a list of strategies for a given parcel
  - Batch prediction over multiple records

The ranker only uses pre-simulation features (parcel geometry + strategy +
road graph from cheap candidate generation), so it can rank strategies before
running the expensive generate_subdivision() call.

Usage:
    ranker = StrategyRanker.load()
    score = ranker.predict_one(parcel_record, strategy_dict, road_graph_dict)
    ranked = ranker.rank_strategies(parcel_record, strategy_list, road_graph_list)
"""

from __future__ import annotations

import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.training.feature_extractor import (
    ALL_FEATURE_NAMES,
    extract_features,
    records_to_arrays,
)

DEFAULT_MODEL_PATH = REPO_ROOT / "model_lab" / "models" / "strategy_ranker.pkl"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RankerPrediction:
    strategy: dict
    predicted_score: float
    rank: int   # 1 = best

    def __repr__(self) -> str:
        return (
            f"RankerPrediction(rank={self.rank}, "
            f"road_type={self.strategy.get('road_type')}, "
            f"density={self.strategy.get('density_goal')}, "
            f"score={self.predicted_score:.4f})"
        )


# ---------------------------------------------------------------------------
# Ranker class
# ---------------------------------------------------------------------------

class StrategyRanker:
    """
    Wraps the trained sklearn model with a clean inference API.

    Load via StrategyRanker.load() — do not instantiate directly.
    """

    def __init__(self, model, feature_names: List[str], metadata: dict) -> None:
        self._model = model
        self._feature_names = feature_names
        self.metadata = metadata

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "StrategyRanker":
        """Load a saved ranker from a .pkl file."""
        model_path = Path(path) if path else DEFAULT_MODEL_PATH
        if not model_path.exists():
            raise FileNotFoundError(
                f"No trained model found at {model_path}.\n"
                "Run model_lab/training/train_strategy_ranker.py first."
            )
        with open(model_path, "rb") as f:
            payload = pickle.load(f)
        return cls(
            model=payload["model"],
            feature_names=payload.get("feature_names", ALL_FEATURE_NAMES),
            metadata=payload.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Core prediction
    # ------------------------------------------------------------------

    def _build_record(
        self,
        parcel_area_sqft: float,
        parcel_polygon: dict,
        strategy: dict,
        road_graph: dict,
    ) -> dict:
        """Assemble a minimal record dict compatible with extract_features."""
        return {
            "parcel_area_sqft": parcel_area_sqft,
            "parcel_polygon": parcel_polygon,
            "strategy": strategy,
            "road_graph": road_graph,
            "score": {"overall_score": 0.0},   # placeholder — not used for inference
        }

    def predict_one(
        self,
        parcel_area_sqft: float,
        parcel_polygon: dict,
        strategy: dict,
        road_graph: dict,
    ) -> float:
        """
        Predict the layout score for a single (parcel, strategy, road_graph) triple.

        Args:
            parcel_area_sqft: parcel area in square feet
            parcel_polygon:   GeoJSON geometry dict
            strategy:         dict with road_type, entry_point, density_goal, culdesac_count
            road_graph:       road graph dict from extract_road_graph().to_dict()

        Returns:
            predicted overall_score (float)
        """
        record = self._build_record(parcel_area_sqft, parcel_polygon, strategy, road_graph)
        feat = extract_features(record)
        row = np.array([[feat.get(n, 0.0) for n in self._feature_names]], dtype=np.float32)
        return float(self._model.predict(row)[0])

    def predict_batch(self, records: List[dict]) -> np.ndarray:
        """Predict scores for a list of already-assembled JSONL-format records."""
        X, _, _ = records_to_arrays(records, feature_names=self._feature_names)
        return self._model.predict(X)

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    def rank_strategies(
        self,
        parcel_area_sqft: float,
        parcel_polygon: dict,
        strategies: List[dict],
        road_graphs: List[dict],
        top_n: Optional[int] = None,
    ) -> List[RankerPrediction]:
        """
        Rank a list of strategies for a given parcel.

        Args:
            parcel_area_sqft: parcel area in sqft
            parcel_polygon:   GeoJSON geometry
            strategies:       list of strategy dicts
            road_graphs:      list of road graph dicts (one per strategy)
            top_n:            if set, return only the top N results

        Returns:
            list of RankerPrediction sorted by predicted_score descending
        """
        if len(strategies) != len(road_graphs):
            raise ValueError(
                f"strategies ({len(strategies)}) and road_graphs ({len(road_graphs)}) "
                "must have equal length"
            )

        records = [
            self._build_record(parcel_area_sqft, parcel_polygon, s, g)
            for s, g in zip(strategies, road_graphs)
        ]
        scores = self.predict_batch(records)

        predictions = [
            RankerPrediction(strategy=s, predicted_score=float(sc), rank=0)
            for s, sc in zip(strategies, scores)
        ]
        predictions.sort(key=lambda p: p.predicted_score, reverse=True)
        for i, pred in enumerate(predictions):
            pred.rank = i + 1

        return predictions[:top_n] if top_n else predictions

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        m = self.metadata
        return (
            f"StrategyRanker({m.get('model_type', '?')}  "
            f"R²={m.get('test_r2', 0):.4f}  "
            f"RMSE={m.get('test_rmse', 0):.4f}  "
            f"rank_acc={m.get('ranking_accuracy', 0):.1%})"
        )
