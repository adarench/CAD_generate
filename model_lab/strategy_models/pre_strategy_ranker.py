"""
Pre-Strategy Ranker — model_lab

Inference module for the pre-simulation strategy ranker.

Uses only parcel geometry + strategy parameters to rank strategies
BEFORE any road graph extraction or layout simulation.

This is Stage 1 in the two-stage ranking architecture:
  Stage 1 (pre-ranker):    parcel + strategy       → rough score estimate
  Stage 2 (post-ranker):   parcel + strategy + graph → refined score estimate

Usage:
    ranker = PreStrategyRanker.load()
    ranked = ranker.rank_strategies(parcel_polygon, area_sqft, strategies)
    top_5  = ranked[:5]

No production code is modified.
"""

from __future__ import annotations

import pickle
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.training.pre_ranker_feature_extractor import (
    ALL_PRE_RANKER_FEATURE_NAMES,
    extract_pre_ranker_features,
)

DEFAULT_MODEL_PATH = REPO_ROOT / "model_lab" / "models" / "pre_strategy_ranker.pkl"


@dataclass
class PreRankerPrediction:
    strategy: dict
    predicted_score: float
    rank: int        # 1 = best

    def __repr__(self) -> str:
        s = self.strategy
        return (
            f"PreRankerPrediction(rank={self.rank}, "
            f"road={s.get('road_type')}, density={s.get('density_goal')}, "
            f"score={self.predicted_score:.4f})"
        )


class PreStrategyRanker:
    """
    Pre-simulation strategy ranker.

    Scores strategies using parcel geometry + strategy parameters only.
    No road graph, no simulation output required.

    Load via PreStrategyRanker.load() — do not instantiate directly.
    """

    def __init__(self, model, feature_names: List[str], metadata: dict) -> None:
        self._model = model
        self._feature_names = feature_names
        self.metadata = metadata

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "PreStrategyRanker":
        model_path = Path(path) if path else DEFAULT_MODEL_PATH
        if not model_path.exists():
            raise FileNotFoundError(
                f"No pre-ranker model found at {model_path}.\n"
                "Run model_lab/training/train_pre_strategy_ranker.py first."
            )
        with open(model_path, "rb") as f:
            payload = pickle.load(f)
        return cls(
            model=payload["model"],
            feature_names=payload.get("feature_names", ALL_PRE_RANKER_FEATURE_NAMES),
            metadata=payload.get("metadata", {}),
        )

    def _build_record(
        self,
        parcel_polygon: dict,
        parcel_area_sqft: float,
        strategy: dict,
    ) -> dict:
        return {
            "parcel_area_sqft": parcel_area_sqft,
            "parcel_polygon":   parcel_polygon,
            "strategy":         strategy,
            "score":            {"overall_score": 0.0},  # placeholder
        }

    def predict_one(
        self,
        parcel_polygon: dict,
        parcel_area_sqft: float,
        strategy: dict,
    ) -> float:
        record = self._build_record(parcel_polygon, parcel_area_sqft, strategy)
        feat = extract_pre_ranker_features(record)
        row = np.array([[feat.get(n, 0.0) for n in self._feature_names]], dtype=np.float32)
        return float(self._model.predict(row)[0])

    def predict_batch(
        self,
        parcel_polygon: dict,
        parcel_area_sqft: float,
        strategies: List[dict],
    ) -> np.ndarray:
        records = [
            self._build_record(parcel_polygon, parcel_area_sqft, s)
            for s in strategies
        ]
        rows = []
        for rec in records:
            feat = extract_pre_ranker_features(rec)
            rows.append([feat.get(n, 0.0) for n in self._feature_names])
        X = np.array(rows, dtype=np.float32)
        return self._model.predict(X)

    def rank_strategies(
        self,
        parcel_polygon: dict,
        parcel_area_sqft: float,
        strategies: List[dict],
        top_n: Optional[int] = None,
    ) -> List[PreRankerPrediction]:
        """
        Rank strategies by predicted score (no road graph or simulation needed).

        Args:
            parcel_polygon:   GeoJSON geometry
            parcel_area_sqft: parcel area in square feet
            strategies:       list of strategy dicts
            top_n:            if set, return only the top N results

        Returns:
            list of PreRankerPrediction sorted by predicted_score descending
        """
        scores = self.predict_batch(parcel_polygon, parcel_area_sqft, strategies)
        predictions = [
            PreRankerPrediction(strategy=s, predicted_score=float(sc), rank=0)
            for s, sc in zip(strategies, scores)
        ]
        predictions.sort(key=lambda p: p.predicted_score, reverse=True)
        for i, p in enumerate(predictions):
            p.rank = i + 1
        return predictions[:top_n] if top_n else predictions

    def __repr__(self) -> str:
        m = self.metadata
        return (
            f"PreStrategyRanker({m.get('model_type', '?')}  "
            f"stage=pre-simulation  "
            f"R²={m.get('test_r2', 0):.4f}  "
            f"features={m.get('feature_count', '?')}"
            f"  [{m.get('n_parcel_features','?')}p+{m.get('n_strategy_features','?')}s])"
        )
