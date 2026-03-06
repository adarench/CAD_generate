from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from openai import OpenAI

from .constraints import Easement, Lots, Parcel, Road, SubdivisionConstraints


AREA_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*acre", re.IGNORECASE)
LOT_PATTERN = re.compile(r"(\d+)\s+lots?", re.IGNORECASE)
WIDTH_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b", re.IGNORECASE)


def parse_prompt(prompt: str, model: str = "gpt-4.1-mini") -> SubdivisionConstraints:
    """
    Parse natural language into validated subdivision constraints.

    The parser prefers OpenAI structured output when an API key is configured.
    It falls back to a local regex parser so the prototype remains runnable offline.
    """

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            return _parse_with_openai(prompt, model=model)
        except Exception:
            pass
    return _parse_with_regex(prompt)


def _parse_with_openai(prompt: str, model: str) -> SubdivisionConstraints:
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract subdivision design constraints. "
                    "Return JSON only. Use rectangle parcels for this prototype."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "subdivision_constraints",
                "schema": _json_schema(),
            },
        },
    )
    content = response.choices[0].message.content
    payload = json.loads(content)
    return SubdivisionConstraints.model_validate(payload)


def _json_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["parcel", "lots", "road", "easement"],
        "properties": {
            "parcel": {
                "type": "object",
                "additionalProperties": False,
                "required": ["shape", "area_acres"],
                "properties": {
                    "shape": {"type": "string", "enum": ["rectangle"]},
                    "area_acres": {"type": "number", "exclusiveMinimum": 0},
                    "aspect_ratio": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "default": 1.5,
                    },
                },
            },
            "lots": {
                "type": "object",
                "additionalProperties": False,
                "required": ["count"],
                "properties": {"count": {"type": "integer", "minimum": 1}},
            },
            "road": {
                "type": "object",
                "additionalProperties": False,
                "required": ["orientation", "width_ft"],
                "properties": {
                    "orientation": {
                        "type": "string",
                        "enum": ["north_south", "east_west"],
                    },
                    "width_ft": {"type": "number", "exclusiveMinimum": 0},
                },
            },
            "easement": {
                "type": "object",
                "additionalProperties": False,
                "required": ["width_ft"],
                "properties": {"width_ft": {"type": "number", "minimum": 0}},
            },
        },
    }


def _parse_with_regex(prompt: str) -> SubdivisionConstraints:
    lowered = prompt.lower()

    area_acres = _extract_float(AREA_PATTERN, prompt, default=10.0)
    lot_count = int(_extract_float(LOT_PATTERN, prompt, default=24))

    orientation = "north_south"
    if "east west" in lowered or "east-west" in lowered:
        orientation = "east_west"
    if "north south" in lowered or "north-south" in lowered:
        orientation = "north_south"

    road_width = _extract_road_width(lowered, default=40.0)
    easement_width = _extract_easement_width(lowered, default=10.0)

    return SubdivisionConstraints(
        parcel=Parcel(shape="rectangle", area_acres=area_acres),
        lots=Lots(count=lot_count),
        road=Road(orientation=orientation, width_ft=road_width),
        easement=Easement(width_ft=easement_width),
    )


def _extract_float(pattern: re.Pattern[str], text: str, default: float) -> float:
    match = pattern.search(text)
    if not match:
        return default
    return float(match.group(1))


def _extract_road_width(text: str, default: float) -> float:
    patterns = (
        r"(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b(?:\s+wide)?\s+(?:road|collector|street)\b",
        r"(?:road|collector|street)\b[^,.]{0,12}?(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b\s+wide\b",
        r"(?:road|collector|street)\b[^,.]{0,16}?\bwidth\b[^,.]{0,8}?(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return default


def _extract_easement_width(text: str, default: float) -> float:
    patterns = (
        r"(?:utility\s+)?easements?\b[^,.]{0,16}?(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b",
        r"(\d+(?:\.\d+)?)\s*(?:foot|feet|ft)\b(?:\s+wide)?\s+(?:utility\s+)?easements?\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return default
