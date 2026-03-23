"""
Build Pre-Ranker Dataset — model_lab

Reads the full layout JSONL dataset and converts each record to a
pre-simulation feature set (parcel + strategy only, no road graph or
layout metrics).

Input:
    model_lab/datasets/layout_training/layout_examples.jsonl

Output:
    model_lab/datasets/layout_training/pre_ranker_dataset.jsonl

Each output record:
    {
        "parcel_id":        str,
        "parcel_source":    str,
        "features":         {<parcel + strategy feature dict>},
        "score":            {"overall_score": float, "yield_score": float,
                             "efficiency_score": float},
    }

The `features` dict contains ONLY pre-simulation inputs.
No production code is modified.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from model_lab.training.pre_ranker_feature_extractor import (
    ALL_PRE_RANKER_FEATURE_NAMES,
    extract_pre_ranker_features,
)

INPUT_PATH  = REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "layout_examples.jsonl"
OUTPUT_PATH = REPO_ROOT / "model_lab" / "datasets" / "layout_training" / "pre_ranker_dataset.jsonl"


def convert(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> int:
    print(f"Reading  : {input_path}")
    records = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    print(f"Records  : {len(records)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for rec in records:
            try:
                features = extract_pre_ranker_features(rec)
                score    = rec.get("score", {})
                out_rec  = {
                    "parcel_id":     rec.get("parcel_id", ""),
                    "parcel_source": rec.get("parcel_source", ""),
                    "features":      features,
                    "score": {
                        "overall_score":    float(score.get("overall_score",    0.0)),
                        "yield_score":      float(score.get("yield_score",      0.0)),
                        "efficiency_score": float(score.get("efficiency_score", 0.0)),
                    },
                }
                out.write(json.dumps(out_rec) + "\n")
                written += 1
            except Exception as exc:
                print(f"  WARN skipping {rec.get('unit_id','?')}: {exc}")

    print(f"Written  : {written} records → {output_path}")
    print(f"Features : {len(ALL_PRE_RANKER_FEATURE_NAMES)}"
          f"  ({len(ALL_PRE_RANKER_FEATURE_NAMES) - 16} parcel + 16 strategy)")

    # Quick score distribution check
    import numpy as np
    scores = [json.loads(l)["score"]["overall_score"]
              for l in open(output_path) if l.strip()]
    arr = np.array(scores)
    print(f"\nScore distribution:")
    print(f"  min={arr.min():.3f}  p25={np.percentile(arr,25):.3f}"
          f"  p50={np.percentile(arr,50):.3f}  p75={np.percentile(arr,75):.3f}"
          f"  max={arr.max():.3f}  mean={arr.mean():.3f}")

    return written


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Build pre-ranker dataset from layout JSONL.")
    parser.add_argument("--input",  type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    convert(args.input, args.output)


if __name__ == "__main__":
    main()
