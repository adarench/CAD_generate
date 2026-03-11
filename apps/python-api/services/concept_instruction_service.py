from __future__ import annotations

import re
from typing import Any

from ai_subdivision.ai_parser import parse_prompt

from schemas import ConceptInstruction, TopologyEnum


DEFAULT_CONSTRAINTS: dict[str, Any] = {
    "minFrontage": 60,
    "minDepth": 110,
    "minArea": 6000,
    "roadWidth": 40,
    "easementWidth": 12,
    "lotCount": 32,
    "roadOrientation": "north_south",
}


class ConceptInstructionService:
    def interpret(self, text: str | None) -> ConceptInstruction | None:
        if not text or not text.strip():
            return None

        lowered = text.lower()
        included: list[TopologyEnum] = []
        excluded: list[TopologyEnum] = []
        edge_conditions: list[str] = []

        if self._mentions_any(lowered, ["cul-de-sac", "cul de sac", "culdesac"]):
            included.append(TopologyEnum.culdesac)
        if "loop" in lowered:
            included.append(TopologyEnum.loop)
        if self._mentions_any(lowered, ["spine", "collector road", "central collector"]):
            included.append(TopologyEnum.spine)
        if "parallel" in lowered and not self._mentions_any(
            lowered,
            ["avoid parallel", "avoid parallel roads", "avoid parallel collectors", "no parallel"],
        ):
            included.append(TopologyEnum.parallel)

        excluded.extend(self._parse_excluded_topologies(lowered))
        included = [item for item in self._unique_topologies(included) if item not in excluded]

        topology_mode: str = "prefer"
        if included and (
            "instead of" in lowered
            or "avoid " in lowered
            or "only " in lowered
            or "do not use" in lowered
            or "don't use" in lowered
        ):
            topology_mode = "strict"

        density_intent = None
        if self._mentions_any(
            lowered,
            [
                "reduce density",
                "lower density",
                "fewer lots",
                "larger lots",
                "increase average lot size",
                "reduce the number of lots",
            ],
        ):
            density_intent = "low"
        elif self._mentions_any(
            lowered,
            [
                "maximize yield",
                "maximize lots",
                "more lots",
                "increase density",
                "higher density",
            ],
        ):
            density_intent = "maximize"
        elif self._mentions_any(
            lowered,
            [
                "moderate density",
                "balanced density",
                "simplify the layout",
                "simplify road layout",
            ],
        ):
            density_intent = "moderate"

        road_intent_parts: list[str] = []
        if self._mentions_any(lowered, ["collector", "collector road", "central collector"]):
            road_intent_parts.append("collector-led street structure")
        if self._mentions_any(lowered, ["local streets", "perpendicular local streets"]):
            road_intent_parts.append("local street network")
        if self._mentions_any(lowered, ["north-south", "north south"]):
            road_intent_parts.append("north-south orientation")
        elif self._mentions_any(lowered, ["east-west", "east west"]):
            road_intent_parts.append("east-west orientation")

        lot_intent_parts: list[str] = []
        if self._mentions_any(lowered, ["larger lots", "increase average lot size", "larger homesites"]):
            lot_intent_parts.append("favor larger lots")
        if self._mentions_any(lowered, ["reduce density", "fewer lots"]):
            lot_intent_parts.append("reduce lot yield")
        if self._mentions_any(lowered, ["maximize yield", "more lots", "increase density"]):
            lot_intent_parts.append("push yield")

        for match in re.findall(r"(north|south|east|west|northern|southern|eastern|western)\s+edge", lowered):
            edge_conditions.append(f"{match} edge emphasis")

        notes = None
        if self._mentions_any(lowered, ["simplify", "simpler", "cleaner layout"]):
            notes = "Favor a cleaner, easier-to-read neighborhood structure."
        elif not included and not excluded and not density_intent:
            notes = text.strip()

        return ConceptInstruction(
            topologyPreferences=included,
            excludedTopologies=excluded,
            topologyMode=topology_mode,
            densityIntent=density_intent,
            roadIntent=", ".join(road_intent_parts) or None,
            lotIntent=", ".join(lot_intent_parts) or None,
            edgeConditions=edge_conditions,
            notes=notes,
        )

    def apply(
        self,
        design_constraints: dict[str, Any],
        request_topologies: list[TopologyEnum],
        strict_topology: bool,
        concept_text: str | None,
    ) -> tuple[dict[str, Any], list[str], bool, ConceptInstruction | None, str | None]:
        constraints = {
            **DEFAULT_CONSTRAINTS,
            **self._prompt_constraints(concept_text),
            **design_constraints,
        }
        instruction = self.interpret(concept_text)
        if instruction is None:
            selected = [pref.value for pref in request_topologies if pref != TopologyEnum.all]
            summary = "Manual feasibility layout using the current parcel assumptions."
            return constraints, selected, strict_topology, None, summary

        if instruction.densityIntent == "low":
            constraints["lotCount"] = max(8, int(round(float(constraints["lotCount"]) * 0.78)))
            constraints["minArea"] = int(round(float(constraints["minArea"]) * 1.2))
            constraints["minFrontage"] = int(round(float(constraints["minFrontage"]) * 1.1))
            constraints["minDepth"] = int(round(float(constraints["minDepth"]) * 1.06))
        elif instruction.densityIntent == "moderate":
            constraints["lotCount"] = max(8, int(round(float(constraints["lotCount"]) * 0.92)))
        elif instruction.densityIntent == "maximize":
            constraints["lotCount"] = max(8, int(round(float(constraints["lotCount"]) * 1.18)))
            constraints["minArea"] = max(4500, int(round(float(constraints["minArea"]) * 0.93)))
            constraints["minFrontage"] = max(50, int(round(float(constraints["minFrontage"]) * 0.95)))

        road_intent = (instruction.roadIntent or "").lower()
        if "collector" in road_intent:
            constraints["roadWidth"] = max(float(constraints["roadWidth"]), 44)
        if "east-west" in road_intent:
            constraints["roadOrientation"] = "east_west"
        elif "north-south" in road_intent:
            constraints["roadOrientation"] = "north_south"

        selected = [pref.value for pref in request_topologies if pref != TopologyEnum.all]
        if instruction.topologyPreferences:
            selected = self._unique_values([*(pref.value for pref in instruction.topologyPreferences), *selected])
        excluded = {pref.value for pref in instruction.excludedTopologies}
        if excluded:
            selected = [topology for topology in selected if topology not in excluded]

        resolved_strict = strict_topology or instruction.topologyMode == "strict"
        summary = self._build_summary(instruction)
        return constraints, selected, resolved_strict, instruction, summary

    def _prompt_constraints(self, concept_text: str | None) -> dict[str, Any]:
        if not concept_text or not concept_text.strip():
            return {}
        try:
            parsed = parse_prompt(concept_text)
        except Exception:
            return {}
        return {
            "lotCount": int(parsed.lots.count),
            "roadOrientation": parsed.road.orientation,
            "roadWidth": float(parsed.road.width_ft),
            "easementWidth": float(parsed.easement.width_ft),
        }

    def _build_summary(self, instruction: ConceptInstruction) -> str:
        phrases: list[str] = []
        if instruction.topologyPreferences:
            phrases.append(
                "prioritize "
                + ", ".join(pref.value.replace("culdesac", "cul-de-sac") for pref in instruction.topologyPreferences)
            )
        if instruction.densityIntent:
            phrases.append(f"{instruction.densityIntent} density")
        if instruction.roadIntent:
            phrases.append(instruction.roadIntent)
        if instruction.lotIntent:
            phrases.append(instruction.lotIntent)
        if instruction.edgeConditions:
            phrases.append("edge focus: " + ", ".join(instruction.edgeConditions))
        if instruction.notes:
            phrases.append(instruction.notes)
        if not phrases:
            return "Parcel-specific concept layout generated from the planner brief."
        return "Concept plan brief: " + "; ".join(phrases) + "."

    def _parse_excluded_topologies(self, lowered: str) -> list[TopologyEnum]:
        mappings = {
            TopologyEnum.parallel: ["avoid parallel", "avoid parallel roads", "avoid parallel collectors", "no parallel"],
            TopologyEnum.loop: ["instead of loops", "avoid loops", "no loops", "without loops"],
            TopologyEnum.culdesac: [
                "avoid cul-de-sacs",
                "avoid cul de sacs",
                "no cul-de-sacs",
                "without cul-de-sacs",
            ],
            TopologyEnum.spine: ["avoid spine", "no spine road", "without a spine road"],
        }
        excluded: list[TopologyEnum] = []
        for topology, patterns in mappings.items():
            if self._mentions_any(lowered, patterns):
                excluded.append(topology)
        return self._unique_topologies(excluded)

    def _mentions_any(self, text: str, patterns: list[str]) -> bool:
        return any(pattern in text for pattern in patterns)

    def _unique_topologies(self, values: list[TopologyEnum]) -> list[TopologyEnum]:
        seen: set[TopologyEnum] = set()
        result: list[TopologyEnum] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result

    def _unique_values(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result
