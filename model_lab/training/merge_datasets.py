"""
Dataset Merger — model_lab Phase 10

Combines multiple graph_training-compatible datasets into a single
unified training set for model retraining.

Sources merged (all graph_training.jsonl format):
  1. model_lab/datasets/graph_training.jsonl     — synthetic baseline (1549 records)
  2. model_lab/datasets/layout_experience.jsonl  — production experience (if exists)
  3. Any additional user-supplied JSONL paths

Output:
  model_lab/datasets/merged_graph_training.jsonl

Usage:
    python -m model_lab.training.merge_datasets [options]

    Options:
      --include-experience   Include production layout_experience.jsonl
      --extra <path>         Additional JSONL files to merge (repeatable)
      --output <path>        Output path (default: merged_graph_training.jsonl)
      --min-score <float>    Minimum score threshold (default: 0.0)
      --max-score <float>    Maximum score threshold (default: 3.0)
      --verbose

No production code is imported.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DATASETS_DIR = REPO_ROOT / "model_lab" / "datasets"

SYNTHETIC_PATH   = DATASETS_DIR / "graph_training.jsonl"
EXPERIENCE_PATH  = DATASETS_DIR / "layout_experience.jsonl"
DEFAULT_OUTPUT   = DATASETS_DIR / "merged_graph_training.jsonl"


# ---------------------------------------------------------------------------
# Record loading
# ---------------------------------------------------------------------------

def load_jsonl(path: Path, label: str = "", verbose: bool = True) -> List[Dict]:
    """Load records from a JSONL file. Returns empty list if file not found."""
    path = Path(path)
    if not path.exists():
        if verbose:
            print(f"  [skip] {label or path.name} not found")
        return []

    records = []
    errors  = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                errors += 1

    if verbose:
        msg = f"  Loaded {len(records):5d} records from {path.name}"
        if errors:
            msg += f"  ({errors} parse errors)"
        print(msg)
    return records


# ---------------------------------------------------------------------------
# Quality filtering
# ---------------------------------------------------------------------------

def _has_required_keys(rec: Dict) -> bool:
    required = {"parcel_id", "parcel_features", "graph_features",
                "generator_type", "score"}
    return required.issubset(rec.keys())


def _feature_vector_valid(rec: Dict) -> bool:
    pf = rec.get("parcel_features", {})
    gf = rec.get("graph_features", {})
    if not isinstance(pf, dict) or not isinstance(gf, dict):
        return False
    # Check that at least one feature has a non-zero value
    pf_vals = list(pf.values())
    gf_vals = list(gf.values())
    return any(v != 0.0 for v in pf_vals) and any(v != 0.0 for v in gf_vals)


def filter_records(
    records: List[Dict],
    min_score: float = 0.0,
    max_score: float = 3.0,
    require_lots: bool = True,
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Apply quality filters. Returns (kept, rejection_counts).
    """
    kept = []
    rejects: Dict[str, int] = defaultdict(int)

    for rec in records:
        score = float(rec.get("score", 0.0))

        if not _has_required_keys(rec):
            rejects["missing_keys"] += 1
            continue
        if score < min_score or score > max_score:
            rejects["score_oob"] += 1
            continue
        if not _feature_vector_valid(rec):
            rejects["zero_features"] += 1
            continue
        if require_lots and int(rec.get("lot_count", 0)) < 1:
            rejects["no_lots"] += 1
            continue

        kept.append(rec)

    return kept, dict(rejects)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(records: List[Dict]) -> Tuple[List[Dict], int]:
    """
    Remove duplicate records.

    A record is a duplicate if another record has the same
    (parcel_id, generator_type, score) tuple (rounded to 4 dp).
    """
    seen: set = set()
    unique: List[Dict] = []
    n_dupes = 0

    for rec in records:
        key = (
            rec.get("parcel_id", ""),
            rec.get("generator_type", ""),
            round(float(rec.get("score", 0.0)), 4),
        )
        if key in seen:
            n_dupes += 1
        else:
            seen.add(key)
            unique.append(rec)

    return unique, n_dupes


# ---------------------------------------------------------------------------
# Dataset statistics
# ---------------------------------------------------------------------------

def dataset_stats(records: List[Dict]) -> Dict[str, Any]:
    """Compute summary statistics for a dataset."""
    if not records:
        return {}

    import math

    scores = [float(r.get("score", 0)) for r in records]
    lot_counts = [int(r.get("lot_count", 0)) for r in records]
    parcel_ids = {r.get("parcel_id", "") for r in records}
    type_counts = Counter(r.get("generator_type", "unknown") for r in records)
    sources = Counter(r.get("source", "synthetic") for r in records)

    def _mean(xs): return sum(xs) / max(len(xs), 1)
    def _std(xs):
        m = _mean(xs)
        return math.sqrt(sum((x - m)**2 for x in xs) / max(len(xs) - 1, 1))

    return {
        "n_records":     len(records),
        "n_parcels":     len(parcel_ids),
        "score_mean":    round(_mean(scores), 4),
        "score_std":     round(_std(scores), 4),
        "score_min":     round(min(scores), 4),
        "score_max":     round(max(scores), 4),
        "lot_count_mean": round(_mean(lot_counts), 1),
        "type_counts":   dict(type_counts),
        "source_counts": dict(sources),
    }


def print_stats(stats: Dict[str, Any], title: str = "") -> None:
    if title:
        print(f"\n  {title}")
    print(f"    records:     {stats.get('n_records', 0)}")
    print(f"    parcels:     {stats.get('n_parcels', 0)}")
    print(f"    score:       {stats.get('score_mean', 0):.4f} ± {stats.get('score_std', 0):.4f}  "
          f"[{stats.get('score_min', 0):.4f}, {stats.get('score_max', 0):.4f}]")
    print(f"    avg lots:    {stats.get('lot_count_mean', 0):.1f}")
    tc = stats.get("type_counts", {})
    if tc:
        type_str = "  ".join(f"{k}={v}" for k, v in sorted(tc.items()))
        print(f"    types:       {type_str}")
    sc = stats.get("source_counts", {})
    if sc:
        src_str = "  ".join(f"{k}={v}" for k, v in sorted(sc.items()))
        print(f"    sources:     {src_str}")


# ---------------------------------------------------------------------------
# Main merge function
# ---------------------------------------------------------------------------

def merge_datasets(
    include_experience:  bool = True,
    extra_paths:         Optional[List[Path]] = None,
    output_path:         Path = DEFAULT_OUTPUT,
    min_score:           float = 0.0,
    max_score:           float = 3.0,
    verbose:             bool = True,
) -> Dict[str, Any]:
    """
    Merge datasets from multiple sources.

    Always includes the synthetic baseline (graph_training.jsonl).
    Optionally includes production experience and extra JSONL files.

    Returns a summary dict with dataset statistics.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("=" * 60)
        print("DATASET MERGER")
        print("=" * 60)
        print("\nLoading sources...")

    all_records: List[Dict] = []

    # 1. Synthetic baseline
    synthetic = load_jsonl(SYNTHETIC_PATH, "synthetic baseline", verbose)
    for r in synthetic:
        if "source" not in r:
            r["source"] = "synthetic"
    all_records.extend(synthetic)

    # 2. Production experiences
    if include_experience:
        experience = load_jsonl(EXPERIENCE_PATH, "production experience", verbose)
        all_records.extend(experience)
    elif verbose:
        print(f"  [skip] production experience (--include-experience not set)")

    # 3. Extra sources
    for p in (extra_paths or []):
        extra = load_jsonl(Path(p), str(p), verbose)
        for r in extra:
            if "source" not in r:
                r["source"] = "extra"
        all_records.extend(extra)

    if verbose:
        print(f"\n  Raw total: {len(all_records)} records")

    # Filter + deduplicate
    filtered, rejects = filter_records(
        all_records, min_score=min_score, max_score=max_score,
    )
    if verbose and rejects:
        print(f"  Filtered out: {rejects}")

    unique, n_dupes = deduplicate(filtered)
    if verbose and n_dupes:
        print(f"  Duplicates removed: {n_dupes}")

    # Compute statistics
    stats = dataset_stats(unique)
    if verbose:
        print_stats(stats, f"Merged dataset ({len(unique)} records)")

    # Save
    with open(output_path, "w") as f:
        for rec in unique:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")

    if verbose:
        print(f"\n  Saved to: {output_path.name}")
        print("=" * 60)

    return {
        "output_path":    str(output_path),
        "n_records":      len(unique),
        "n_dupes_removed": n_dupes,
        "n_filtered":     len(all_records) - len(filtered),
        "stats":          stats,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Merge graph_training datasets for model retraining",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--include-experience", action="store_true",
                        help="Include production layout_experience.jsonl")
    parser.add_argument("--extra", nargs="*", default=[],
                        help="Additional JSONL file paths to merge")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help="Output merged JSONL path")
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--max-score", type=float, default=3.0)
    parser.add_argument("--verbose", action="store_true", default=True)
    args = parser.parse_args()

    result = merge_datasets(
        include_experience=args.include_experience,
        extra_paths=[Path(p) for p in args.extra],
        output_path=Path(args.output),
        min_score=args.min_score,
        max_score=args.max_score,
        verbose=args.verbose,
    )
    print(f"\nMerge complete: {result['n_records']} records → {result['output_path']}")
