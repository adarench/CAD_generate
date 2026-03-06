from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class ZoningRules(BaseModel):
    min_frontage_ft: float = Field(default=60.0, gt=0)
    min_depth_ft: float = Field(default=110.0, gt=0)
    min_area_sqft: float = Field(default=6000.0, gt=0)


def load_zoning_rules(path: str | None = None) -> ZoningRules:
    config_path = Path(path) if path else default_zoning_rules_path()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return ZoningRules.model_validate(payload)


def default_zoning_rules_path() -> Path:
    return Path(__file__).resolve().parents[1] / "zoning_rules.json"
