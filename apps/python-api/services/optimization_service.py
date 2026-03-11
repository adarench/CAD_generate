from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ai_subdivision.constraints import Easement, Lots, Parcel, Road, SubdivisionConstraints
from ai_subdivision.dxf_export import export_dxf
from ai_subdivision.geojson_export import layout_to_geojson_bytes
from ai_subdivision.geometry import export_layout_to_cadquery_step
from ai_subdivision.subdivision import summarize_layout
from ai_subdivision.yield_optimizer import optimize_yield
from ai_subdivision.zoning import ZoningRules

from schemas import (
    OptimizationRequest,
    OptimizationResponse,
    ParcelRecord,
    RunDetail,
    RunStatus,
    RunSummary,
    TopologyEnum,
    TopologySummary,
)
from services.concept_instruction_service import ConceptInstructionService
from services.parcel_adapter import adapt_parcel_geometry, lot_label_to_geojson, polygon2d_to_geojson
from services.parcel_service import ParcelService
from services.persistence import PersistenceLayer

EXPORT_ROOT = Path("apps/python-api/data/exports")
EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
PUBLIC_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", "http://127.0.0.1:8000")


class OptimizerService:
    def __init__(self):
        self.persistence = PersistenceLayer()
        self.parcels = ParcelService()
        self.concepts = ConceptInstructionService()

    async def optimize(self, request: OptimizationRequest) -> RunDetail:
        parcel = await self._resolve_parcel(request)
        adapted = adapt_parcel_geometry(parcel.geometryGeoJSON.model_dump())
        boundary = [list(coord) for coord in adapted.parcel_polygon.exterior.coords[:-1]]
        resolved_constraints, preferred, resolved_strict, instruction, concept_summary = self.concepts.apply(
            request.designConstraints,
            request.topologyPreferences,
            request.strictTopology,
            request.conceptText,
        )
        constraints = self._build_constraints(resolved_constraints, boundary)
        zoning = ZoningRules(
            min_frontage_ft=float(resolved_constraints.get("minFrontage", 60)),
            min_depth_ft=float(resolved_constraints.get("minDepth", 110)),
            min_area_sqft=float(resolved_constraints.get("minArea", 6000)),
        )
        allowed = preferred if resolved_strict and preferred else None
        result = optimize_yield(constraints, zoning, allowed_topologies=allowed)
        summary = summarize_layout(constraints, zoning, result.best_layout)
        run_id = str(uuid4())
        exports = self._write_exports(run_id, result.best_layout)
        response = OptimizationResponse(
            runId=run_id,
            winningTopology=result.best_network.topology,
            lotCount=result.lot_count,
            parcelAreaSqft=round(adapted.parcel_polygon.area, 2),
            roadLengthFt=float(summary["road_length_ft"]),
            developableAreaSqft=float(summary["developable_area_sqft"]),
            averageLotAreaSqft=float(summary["average_lot_area_sqft"]),
            candidateSummary=self._candidate_summaries(
                result=result,
                preferred_topologies=preferred,
                strict_topology=resolved_strict,
            ),
            resolvedConstraints=resolved_constraints,
            conceptSummary=concept_summary,
            appliedInstruction=instruction,
            resultGeoJSON=self._geometry_to_geojson(result.best_layout, adapted.projection),
            exports=exports,
        )
        run = RunDetail(
            runId=run_id,
            parcelId=parcel.id,
            status=RunStatus.completed,
            parcel=parcel,
            inputConstraints={
                **resolved_constraints,
                "conceptText": request.conceptText,
                "conceptInstruction": instruction.model_dump(mode="json") if instruction else None,
                "conceptSummary": concept_summary,
            },
            topologyPreferences=preferred or [pref.value for pref in request.topologyPreferences],
            strictTopology=resolved_strict,
            createdAt=datetime.now(timezone.utc),
            response=response,
        )
        await self.persistence.save_run(run)
        return run

    async def get_run(self, run_id: str) -> RunDetail | None:
        return await self.persistence.get_run(run_id)

    async def get_latest_run_for_parcel(self, parcel_id: str) -> RunDetail | None:
        return await self.persistence.get_latest_run_for_parcel(parcel_id)

    async def list_runs(self, limit: int = 10) -> list[RunSummary]:
        return await self.persistence.list_runs(limit)

    def response_only(self, run: RunDetail) -> OptimizationResponse:
        return run.response

    async def _resolve_parcel(self, request: OptimizationRequest) -> ParcelRecord:
        if request.parcelId:
            parcel = await self.parcels.get_parcel(request.parcelId)
            if not parcel:
                raise ValueError(f"Parcel '{request.parcelId}' was not found in cache.")
            return parcel
        assert request.parcel is not None
        parcel = ParcelRecord(
            id=request.parcel.id,
            county=request.parcel.county,
            apn=request.parcel.apn,
            sourceProvider=request.parcel.sourceProvider,
            sourceDataset=request.parcel.sourceDataset,
            sourceObjectId=request.parcel.sourceObjectId,
            geometryGeoJSON=request.parcel.geometry,
            centroid=request.parcel.centroid,
            areaSqft=request.parcel.areaSqft,
            areaAcres=request.parcel.areaAcres,
            address=request.parcel.address,
            ownerName=request.parcel.ownerName,
            zoningCode=None,
            landUse=None,
            rawAttributes=request.parcel.rawAttributes,
            fetchedAt=request.parcel.fetchedAt,
        )
        return await self.parcels.ensure_cached(parcel)

    def _geometry_to_geojson(self, layout, projection):
        features = []
        for layer, polygons in layout.polygon_groups().items():
            for polygon in polygons:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {"layer": layer},
                        "geometry": polygon2d_to_geojson(polygon, projection),
                    }
                )
        for label in layout.lot_labels:
            features.append(
                {
                    "type": "Feature",
                    "properties": {"layer": "lot_labels", "text": label.text},
                    "geometry": lot_label_to_geojson(label, projection),
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def _build_constraints(
        self, design_constraints: dict[str, object], boundary: list[list[float]]
    ) -> SubdivisionConstraints:
        return SubdivisionConstraints(
            parcel=Parcel(shape="polygon", boundary=boundary, area_acres=None, aspect_ratio=1.5),
            lots=Lots(count=int(design_constraints.get("lotCount", 24))),
            road=Road(
                orientation=str(design_constraints.get("roadOrientation", "north_south")),
                width_ft=float(design_constraints.get("roadWidth", 40)),
            ),
            easement=Easement(width_ft=float(design_constraints.get("easementWidth", 12))),
        )

    def _preferred_topologies(self, request: OptimizationRequest) -> list[str]:
        if request.topologyPreferences and TopologyEnum.all not in request.topologyPreferences:
            return [pref.value for pref in request.topologyPreferences]
        return []

    def _candidate_summaries(
        self,
        result,
        preferred_topologies: list[str],
        strict_topology: bool,
    ) -> list[TopologySummary]:
        grouped: dict[str, dict[str, float]] = defaultdict(
            lambda: {
                "candidatesTested": 0,
                "lots": 0,
                "roadLength": 0.0,
                "developableAreaSqft": 0.0,
            }
        )
        all_topologies = ["parallel", "spine", "loop", "culdesac"]

        for candidate in result.candidate_summary:
            entry = grouped[candidate.topology]
            entry["candidatesTested"] += 1
            if candidate.lot_count >= entry["lots"]:
                entry["lots"] = candidate.lot_count
                entry["roadLength"] = candidate.road_length_ft
                entry["developableAreaSqft"] = candidate.developable_area_sqft

        summaries: list[TopologySummary] = []
        for topology in all_topologies:
            values = grouped[topology]
            requested = topology in preferred_topologies
            winner = topology == result.best_network.topology
            fallback_winner = winner and preferred_topologies and topology not in preferred_topologies

            if winner:
                status = "winner"
            elif requested and values["candidatesTested"] == 0:
                status = "unavailable"
            elif requested:
                status = "preferred"
            elif values["candidatesTested"] > 0:
                status = "tested"
            else:
                status = "not-tested"

            notes = None
            if fallback_winner and not strict_topology:
                notes = "Fallback used. A non-preferred topology produced the winning yield."
            elif requested and values["candidatesTested"] == 0:
                notes = "Requested topology produced no valid candidates for this parcel."
            elif strict_topology and requested and not winner:
                notes = "Strict topology mode limited the optimizer to the requested family."

            summaries.append(
                TopologySummary(
                    topology=topology,
                    candidatesTested=int(values["candidatesTested"]),
                    lots=int(values["lots"]),
                    roadLength=float(values["roadLength"]),
                    developableAreaSqft=float(values["developableAreaSqft"]),
                    status=status,
                    notes=notes,
                )
            )
        return summaries

    def _write_exports(self, run_id: str, layout) -> dict[str, str]:
        run_dir = EXPORT_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        dxf_name = "subdivision_layout.dxf"
        geojson_name = "subdivision_layout.geojson"
        step_name = "subdivision_layout.step"

        export_dxf(layout, output_path=str(run_dir / dxf_name))
        (run_dir / geojson_name).write_bytes(layout_to_geojson_bytes(layout))

        exports = {
            "dxf": f"{PUBLIC_BASE_URL}/exports/{run_id}/{dxf_name}",
            "geojson": f"{PUBLIC_BASE_URL}/exports/{run_id}/{geojson_name}",
            "step": "",
        }
        try:
            export_layout_to_cadquery_step(layout, path=str(run_dir / step_name))
            exports["step"] = f"{PUBLIC_BASE_URL}/exports/{run_id}/{step_name}"
        except RuntimeError:
            exports["step"] = ""
        return exports
