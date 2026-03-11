from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg
from shapely.geometry import Point, box, shape

from schemas import ParcelRecord, ParcelSourceRecord, RunDetail, RunStatus, RunSummary
from services.parcel_adapter import geometry_area_sqft

DATA_PATH = Path("apps/python-api/data")
DATA_PATH.mkdir(parents=True, exist_ok=True)
RUNS_FILE = DATA_PATH / "runs.json"
PARCELS_FILE = DATA_PATH / "parcels.json"


class PersistenceLayer:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        self._runs: dict[str, Any] = self._load_json(RUNS_FILE)
        self._parcels: dict[str, Any] = self._load_json(PARCELS_FILE)

    @property
    def database_enabled(self) -> bool:
        return bool(self.database_url)

    async def save_parcel(self, parcel: ParcelRecord, source: ParcelSourceRecord | None = None) -> None:
        payload = hydrate_parcel_payload(parcel.model_dump(mode="json"))
        self._parcels[parcel.id] = payload
        PARCELS_FILE.write_text(json.dumps(self._parcels, indent=2))
        if self.database_url:
            await self._save_parcel_sql(ParcelRecord.model_validate(payload), source)

    async def get_parcel(self, parcel_id: str) -> ParcelRecord | None:
        if self.database_url:
            record = await self._get_parcel_sql(parcel_id)
            if record:
                return record
        payload = hydrate_parcel_payload(self._parcels.get(parcel_id))
        return ParcelRecord.model_validate(payload) if payload else None

    async def search_parcels_by_apn(self, county: str, apn: str) -> list[ParcelRecord]:
        if self.database_enabled:
            return await self._search_parcels_by_apn_sql(county, apn)
        return self.search_local_parcels_by_apn(county, apn)

    async def search_parcels_by_bounds(
        self,
        county: str,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        limit: int = 150,
    ) -> list[ParcelRecord]:
        if self.database_enabled:
            return await self._search_parcels_by_bounds_sql(
                county=county,
                min_lng=min_lng,
                min_lat=min_lat,
                max_lng=max_lng,
                max_lat=max_lat,
                limit=limit,
            )
        return self.search_local_parcels_by_bounds(
            county=county,
            min_lng=min_lng,
            min_lat=min_lat,
            max_lng=max_lng,
            max_lat=max_lat,
            limit=limit,
        )

    def search_local_parcels_by_apn(self, county: str, apn: str) -> list[ParcelRecord]:
        normalized = normalize_apn(apn)
        results = []
        for payload in self._parcels.values():
            if payload.get("county", "").lower() != county.lower():
                continue
            if normalize_apn(payload.get("apn")) == normalized:
                results.append(ParcelRecord.model_validate(hydrate_parcel_payload(payload)))
        return results

    def search_local_parcels_by_bounds(
        self,
        county: str,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        limit: int = 150,
    ) -> list[ParcelRecord]:
        viewport = box(min_lng, min_lat, max_lng, max_lat)
        matches: list[ParcelRecord] = []
        for payload in self._parcels.values():
            if payload.get("county", "").lower() != county.lower():
                continue
            geometry = payload.get("geometryGeoJSON")
            if not geometry:
                continue
            try:
                if shape(geometry).intersects(viewport):
                    matches.append(ParcelRecord.model_validate(hydrate_parcel_payload(payload)))
            except Exception:
                continue
        matches.sort(key=parcel_sort_key)
        return matches[:limit]

    async def search_parcels_by_point(
        self, county: str, lng: float, lat: float, limit: int = 12
    ) -> list[ParcelRecord]:
        if self.database_enabled:
            return await self._search_parcels_by_point_sql(county=county, lng=lng, lat=lat, limit=limit)
        return self.search_local_parcels_by_point(county=county, lng=lng, lat=lat, limit=limit)

    def search_local_parcels_by_point(
        self, county: str, lng: float, lat: float, limit: int = 12
    ) -> list[ParcelRecord]:
        probe = Point(lng, lat)
        matches: list[ParcelRecord] = []
        for payload in self._parcels.values():
            if payload.get("county", "").lower() != county.lower():
                continue
            geometry = payload.get("geometryGeoJSON")
            if not geometry:
                continue
            try:
                if shape(geometry).intersects(probe):
                    matches.append(ParcelRecord.model_validate(hydrate_parcel_payload(payload)))
            except Exception:
                continue
        matches.sort(key=parcel_sort_key)
        return matches[:limit]

    def list_local_parcels(self) -> list[ParcelRecord]:
        return [
            ParcelRecord.model_validate(hydrate_parcel_payload(payload))
            for payload in self._parcels.values()
            if payload.get("geometryGeoJSON")
        ]

    async def list_recent_parcels(self, limit: int = 8) -> list[ParcelRecord]:
        if self.database_url:
            return await self._list_recent_parcels_sql(limit)
        records = [
            ParcelRecord.model_validate(payload)
            for payload in sorted(
                (hydrate_parcel_payload(item) for item in self._parcels.values()),
                key=lambda item: item.get("fetchedAt", ""),
                reverse=True,
            )
        ]
        return records[:limit]

    async def save_run(self, run: RunDetail) -> None:
        payload = run.model_dump(mode="json")
        self._runs[run.runId] = payload
        RUNS_FILE.write_text(json.dumps(self._runs, indent=2))
        if self.database_url:
            await self._save_run_sql(run)

    async def get_run(self, run_id: str) -> RunDetail | None:
        if self.database_url:
            record = await self._get_run_sql(run_id)
            if record:
                return record
        payload = hydrate_run_payload(self._runs.get(run_id))
        return RunDetail.model_validate(payload) if payload else None

    async def get_latest_run_for_parcel(self, parcel_id: str) -> RunDetail | None:
        if self.database_url:
            return await self._get_latest_run_for_parcel_sql(parcel_id)
        candidates = [hydrate_run_payload(payload) for payload in self._runs.values() if payload.get("parcelId") == parcel_id]
        candidates = [payload for payload in candidates if payload]
        if not candidates:
            return None
        latest = max(candidates, key=lambda item: item.get("createdAt") or item.get("updatedAt") or "")
        return RunDetail.model_validate(latest)

    async def list_runs(self, limit: int = 10) -> list[RunSummary]:
        if self.database_url:
            return await self._list_runs_sql(limit)
        summaries: list[RunSummary] = []
        for payload in sorted(
            self._runs.values(),
            key=lambda item: item.get("createdAt", ""),
            reverse=True,
        )[:limit]:
            created_at = payload.get("createdAt") or payload.get("updatedAt") or "1970-01-01T00:00:00+00:00"
            summaries.append(
                RunSummary(
                    runId=payload["runId"],
                    parcelId=payload["parcelId"],
                    parcelApn=payload.get("parcel", {}).get("apn"),
                    county=payload.get("parcel", {}).get("county"),
                    winningTopology=payload["response"]["winningTopology"],
                    lotCount=payload["response"]["lotCount"],
                    createdAt=created_at,
                    status=payload["status"],
                )
            )
        return summaries

    def _load_json(self, path: Path) -> dict[str, Any]:
        if path.exists():
            return json.loads(path.read_text())
        return {}

    async def _save_parcel_sql(self, parcel: ParcelRecord, source: ParcelSourceRecord | None) -> None:
        conn = await asyncpg.connect(dsn=self.database_url)
        if source:
            await conn.execute(
                """
                INSERT INTO parcel_sources(id, provider, dataset_name, dataset_url, refresh_status, metadata_json)
                VALUES($1, $2, $3, $4, $5, $6::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                  provider = EXCLUDED.provider,
                  dataset_name = EXCLUDED.dataset_name,
                  dataset_url = EXCLUDED.dataset_url,
                  refresh_status = EXCLUDED.refresh_status,
                  metadata_json = EXCLUDED.metadata_json;
                """,
                source.id,
                source.provider,
                source.datasetName,
                source.datasetUrl,
                source.refreshStatus,
                json.dumps(source.metadataJson),
            )
        geometry_json = json.dumps(parcel.geometryGeoJSON.model_dump(mode="json"))
        await conn.execute(
            """
            INSERT INTO parcels(
              id, state, county, apn, source_provider, source_dataset, source_object_id, geometry,
              centroid, area_sqft, area_acres, address, owner_name, zoning_code, land_use,
              raw_attributes, fetched_at, updated_at
            )
            VALUES(
              $1, $2, $3, $4, $5, $6, $7,
              ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON($8), 4326)),
              ST_SetSRID(ST_MakePoint($9, $10), 4326),
              $11, $12, $13, $14, $15, $16, $17::jsonb, $18, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
              county = EXCLUDED.county,
              apn = EXCLUDED.apn,
              source_provider = EXCLUDED.source_provider,
              source_dataset = EXCLUDED.source_dataset,
              source_object_id = EXCLUDED.source_object_id,
              geometry = EXCLUDED.geometry,
              centroid = EXCLUDED.centroid,
              area_sqft = EXCLUDED.area_sqft,
              area_acres = EXCLUDED.area_acres,
              address = EXCLUDED.address,
              owner_name = EXCLUDED.owner_name,
              zoning_code = EXCLUDED.zoning_code,
              land_use = EXCLUDED.land_use,
              raw_attributes = EXCLUDED.raw_attributes,
              fetched_at = EXCLUDED.fetched_at,
              updated_at = NOW();
            """,
            parcel.id,
            parcel.state,
            parcel.county,
            parcel.apn,
            parcel.sourceProvider,
            parcel.sourceDataset,
            parcel.sourceObjectId,
            geometry_json,
            float(parcel.centroid["lng"]),
            float(parcel.centroid["lat"]),
            parcel.areaSqft,
            parcel.areaAcres,
            parcel.address,
            parcel.ownerName,
            parcel.zoningCode,
            parcel.landUse,
            json.dumps(parcel.rawAttributes),
            parcel.fetchedAt,
        )
        await conn.close()

    async def _get_parcel_sql(self, parcel_id: str) -> ParcelRecord | None:
        conn = await asyncpg.connect(dsn=self.database_url)
        row = await conn.fetchrow(
            """
            SELECT
              id, state, county, apn, source_provider, source_dataset, source_object_id,
              ST_AsGeoJSON(geometry)::json AS geometry_geojson,
              ST_X(centroid) AS centroid_lng,
              ST_Y(centroid) AS centroid_lat,
              area_sqft, area_acres, address, owner_name, zoning_code, land_use, raw_attributes,
              fetched_at
            FROM parcels
            WHERE id = $1
            """,
            parcel_id,
        )
        await conn.close()
        return build_parcel_from_row(row) if row else None

    async def _search_parcels_by_apn_sql(self, county: str, apn: str) -> list[ParcelRecord]:
        conn = await asyncpg.connect(dsn=self.database_url)
        normalized = normalize_apn(apn)
        rows = await conn.fetch(
            """
            SELECT
              id, state, county, apn, source_provider, source_dataset, source_object_id,
              ST_AsGeoJSON(geometry)::json AS geometry_geojson,
              ST_X(centroid) AS centroid_lng,
              ST_Y(centroid) AS centroid_lat,
              area_sqft, area_acres, address, owner_name, zoning_code, land_use, raw_attributes,
              fetched_at
            FROM parcels
            WHERE LOWER(county) = LOWER($1)
              AND regexp_replace(COALESCE(apn, ''), '[^0-9A-Za-z]', '', 'g') = $2
            ORDER BY fetched_at DESC
            LIMIT 5
            """,
            county,
            normalized,
        )
        await conn.close()
        return [build_parcel_from_row(row) for row in rows]

    async def _search_parcels_by_bounds_sql(
        self,
        county: str,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        limit: int,
    ) -> list[ParcelRecord]:
        conn = await asyncpg.connect(dsn=self.database_url)
        rows = await conn.fetch(
            """
            SELECT
              id, state, county, apn, source_provider, source_dataset, source_object_id,
              ST_AsGeoJSON(geometry)::json AS geometry_geojson,
              ST_X(centroid) AS centroid_lng,
              ST_Y(centroid) AS centroid_lat,
              area_sqft, area_acres, address, owner_name, zoning_code, land_use, raw_attributes,
              fetched_at
            FROM parcels
            WHERE LOWER(county) = LOWER($1)
              AND geometry && ST_MakeEnvelope($2, $3, $4, $5, 4326)
              AND ST_Intersects(geometry, ST_MakeEnvelope($2, $3, $4, $5, 4326))
            ORDER BY area_sqft ASC NULLS LAST, fetched_at DESC
            LIMIT $6
            """,
            county,
            min_lng,
            min_lat,
            max_lng,
            max_lat,
            limit,
        )
        await conn.close()
        return [build_parcel_from_row(row) for row in rows]

    async def _search_parcels_by_point_sql(
        self, county: str, lng: float, lat: float, limit: int
    ) -> list[ParcelRecord]:
        conn = await asyncpg.connect(dsn=self.database_url)
        rows = await conn.fetch(
            """
            SELECT
              id, state, county, apn, source_provider, source_dataset, source_object_id,
              ST_AsGeoJSON(geometry)::json AS geometry_geojson,
              ST_X(centroid) AS centroid_lng,
              ST_Y(centroid) AS centroid_lat,
              area_sqft, area_acres, address, owner_name, zoning_code, land_use, raw_attributes,
              fetched_at
            FROM parcels
            WHERE LOWER(county) = LOWER($1)
              AND ST_Intersects(geometry, ST_SetSRID(ST_MakePoint($2, $3), 4326))
            ORDER BY area_sqft ASC NULLS LAST, fetched_at DESC
            LIMIT $4
            """,
            county,
            lng,
            lat,
            limit,
        )
        await conn.close()
        return [build_parcel_from_row(row) for row in rows]

    async def _list_recent_parcels_sql(self, limit: int) -> list[ParcelRecord]:
        conn = await asyncpg.connect(dsn=self.database_url)
        rows = await conn.fetch(
            """
            SELECT
              id, state, county, apn, source_provider, source_dataset, source_object_id,
              ST_AsGeoJSON(geometry)::json AS geometry_geojson,
              ST_X(centroid) AS centroid_lng,
              ST_Y(centroid) AS centroid_lat,
              area_sqft, area_acres, address, owner_name, zoning_code, land_use, raw_attributes,
              fetched_at
            FROM parcels
            ORDER BY updated_at DESC NULLS LAST, fetched_at DESC
            LIMIT $1
            """,
            limit,
        )
        await conn.close()
        return [build_parcel_from_row(row) for row in rows]

    async def _save_run_sql(self, run: RunDetail) -> None:
        conn = await asyncpg.connect(dsn=self.database_url)
        await conn.execute(
            """
            INSERT INTO optimization_runs(
              id, parcel_id, input_constraints, preferred_topologies, strict_topology, run_status,
              created_at, updated_at
            )
            VALUES($1, $2, $3::jsonb, $4::jsonb, $5, $6, $7, NOW())
            ON CONFLICT (id) DO UPDATE SET
              input_constraints = EXCLUDED.input_constraints,
              preferred_topologies = EXCLUDED.preferred_topologies,
              strict_topology = EXCLUDED.strict_topology,
              run_status = EXCLUDED.run_status,
              updated_at = NOW();
            """,
            run.runId,
            run.parcelId,
            json.dumps(run.inputConstraints),
            json.dumps(run.topologyPreferences),
            run.strictTopology,
            run.status.value,
            run.createdAt,
        )
        await conn.execute(
            """
            INSERT INTO optimization_results(
              id, run_id, winning_topology, candidate_summary_json, max_lot_count,
              developable_area_sqft, road_length_ft, avg_lot_area_sqft,
              result_geojson, exports_json, created_at, updated_at
            )
            VALUES($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, NOW())
            ON CONFLICT (id) DO UPDATE SET
              winning_topology = EXCLUDED.winning_topology,
              candidate_summary_json = EXCLUDED.candidate_summary_json,
              max_lot_count = EXCLUDED.max_lot_count,
              developable_area_sqft = EXCLUDED.developable_area_sqft,
              road_length_ft = EXCLUDED.road_length_ft,
              avg_lot_area_sqft = EXCLUDED.avg_lot_area_sqft,
              result_geojson = EXCLUDED.result_geojson,
              exports_json = EXCLUDED.exports_json,
              updated_at = NOW();
            """,
            run.runId,
            run.runId,
            run.response.winningTopology,
            json.dumps([item.model_dump(mode="json") for item in run.response.candidateSummary]),
            run.response.lotCount,
            run.response.developableAreaSqft,
            run.response.roadLengthFt,
            run.response.averageLotAreaSqft,
            json.dumps(run.response.resultGeoJSON),
            json.dumps(run.response.exports),
            run.createdAt,
        )
        await conn.close()

    async def _get_run_sql(self, run_id: str) -> RunDetail | None:
        conn = await asyncpg.connect(dsn=self.database_url)
        row = await conn.fetchrow(
            """
            SELECT
              r.id AS run_id,
              r.parcel_id,
              r.input_constraints,
              r.preferred_topologies,
              r.strict_topology,
              r.run_status,
              r.created_at,
              res.winning_topology,
              res.candidate_summary_json,
              res.max_lot_count,
              res.developable_area_sqft,
              res.road_length_ft,
              res.avg_lot_area_sqft,
              res.result_geojson,
              res.exports_json
            FROM optimization_runs r
            JOIN optimization_results res ON res.run_id = r.id
            WHERE r.id = $1
            """,
            run_id,
        )
        parcel = None
        if row:
            parcel = await self._get_parcel_sql(row["parcel_id"])
        await conn.close()
        if not row:
            return None
        input_constraints = row["input_constraints"] or {}
        preferred_topologies = row["preferred_topologies"] or []
        candidate_summary = row["candidate_summary_json"] or []
        result_geojson = row["result_geojson"] or {"type": "FeatureCollection", "features": []}
        exports_json = row["exports_json"] or {}
        if isinstance(input_constraints, str):
            input_constraints = json.loads(input_constraints)
        if isinstance(preferred_topologies, str):
            preferred_topologies = json.loads(preferred_topologies)
        if isinstance(candidate_summary, str):
            candidate_summary = json.loads(candidate_summary)
        if isinstance(result_geojson, str):
            result_geojson = json.loads(result_geojson)
        if isinstance(exports_json, str):
            exports_json = json.loads(exports_json)
        return RunDetail.model_validate(
            {
                "runId": row["run_id"],
                "parcelId": row["parcel_id"],
                "status": row["run_status"],
                "parcel": parcel.model_dump(mode="json") if parcel else None,
                "inputConstraints": input_constraints,
                "topologyPreferences": preferred_topologies,
                "strictTopology": row["strict_topology"] or False,
                "createdAt": row["created_at"] or datetime.now(timezone.utc),
                "response": {
                    "runId": row["run_id"],
                    "winningTopology": row["winning_topology"],
                    "lotCount": row["max_lot_count"],
                    "parcelAreaSqft": parcel.areaSqft if parcel and parcel.areaSqft else 0,
                    "roadLengthFt": row["road_length_ft"],
                    "developableAreaSqft": row["developable_area_sqft"],
                    "averageLotAreaSqft": row["avg_lot_area_sqft"],
                    "candidateSummary": candidate_summary,
                    "resultGeoJSON": result_geojson,
                    "exports": exports_json,
                },
            }
        )

    async def _get_latest_run_for_parcel_sql(self, parcel_id: str) -> RunDetail | None:
        conn = await asyncpg.connect(dsn=self.database_url)
        row = await conn.fetchrow(
            """
            SELECT r.id AS run_id
            FROM optimization_runs r
            WHERE r.parcel_id = $1
            ORDER BY r.created_at DESC
            LIMIT 1
            """,
            parcel_id,
        )
        await conn.close()
        if not row:
            return None
        return await self._get_run_sql(row["run_id"])

    async def _list_runs_sql(self, limit: int) -> list[RunSummary]:
        conn = await asyncpg.connect(dsn=self.database_url)
        rows = await conn.fetch(
            """
            SELECT
              r.id AS run_id,
              r.parcel_id,
              r.run_status,
              r.created_at,
              p.apn,
              p.county,
              res.winning_topology,
              res.max_lot_count
            FROM optimization_runs r
            LEFT JOIN parcels p ON p.id = r.parcel_id
            LEFT JOIN optimization_results res ON res.run_id = r.id
            ORDER BY r.created_at DESC
            LIMIT $1
            """,
            limit,
        )
        await conn.close()
        return [
            RunSummary(
                runId=row["run_id"],
                parcelId=row["parcel_id"],
                parcelApn=row["apn"],
                county=row["county"],
                winningTopology=row["winning_topology"] or "pending",
                lotCount=row["max_lot_count"] or 0,
                createdAt=row["created_at"] or datetime.now(timezone.utc),
                status=row["run_status"] or RunStatus.completed.value,
            )
            for row in rows
        ]


def build_parcel_from_row(row: asyncpg.Record) -> ParcelRecord:
    geometry = row["geometry_geojson"]
    if isinstance(geometry, str):
        geometry = json.loads(geometry)
    area_sqft = round(geometry_area_sqft(geometry), 2) if geometry else None
    raw_attributes = row["raw_attributes"] or {}
    if isinstance(raw_attributes, str):
        raw_attributes = json.loads(raw_attributes)
    source_dataset = normalize_source_dataset(row["source_dataset"], row["county"])
    return ParcelRecord.model_validate(
        {
            "id": row["id"],
            "state": row["state"],
            "county": row["county"],
            "apn": row["apn"],
            "sourceProvider": row["source_provider"],
            "sourceDataset": source_dataset,
            "sourceObjectId": row["source_object_id"],
            "geometryGeoJSON": geometry,
            "centroid": {"lng": row["centroid_lng"], "lat": row["centroid_lat"]},
            "areaSqft": area_sqft,
            "areaAcres": round(area_sqft / 43560.0, 4) if area_sqft else None,
            "address": row["address"],
            "ownerName": row["owner_name"],
            "zoningCode": row["zoning_code"],
            "landUse": row["land_use"],
            "rawAttributes": raw_attributes,
            "fetchedAt": row["fetched_at"] or datetime.now(timezone.utc),
        }
    )


def normalize_apn(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isalnum())


def normalize_source_dataset(value: str | None, county: str | None) -> str | None:
    if not value:
        return value
    if value.startswith("Parcels_"):
        suffix = value.split("Parcels_", 1)[1]
        normalized = "".join(ch for ch in suffix if ch.isalnum())
        return f"Parcels_{normalized}" if normalized else value
    if county:
        return f"Parcels_{''.join(ch for ch in county if ch.isalnum())}"
    return value


def hydrate_parcel_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return payload
    geometry = payload.get("geometryGeoJSON")
    if not geometry:
        return payload
    area_sqft = round(geometry_area_sqft(geometry), 2)
    hydrated = dict(payload)
    hydrated["areaSqft"] = area_sqft
    hydrated["areaAcres"] = round(area_sqft / 43560.0, 4) if area_sqft else None
    return hydrated


def hydrate_run_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return payload
    hydrated = dict(payload)
    parcel_payload = hydrate_parcel_payload(hydrated.get("parcel"))
    if parcel_payload:
        hydrated["parcel"] = parcel_payload
        response = dict(hydrated.get("response") or {})
        response["parcelAreaSqft"] = parcel_payload.get("areaSqft") or response.get("parcelAreaSqft") or 0
        hydrated["response"] = response
    return hydrated


def parcel_sort_key(parcel: ParcelRecord) -> tuple[float, float]:
    area_sqft = float(parcel.areaSqft) if parcel.areaSqft is not None else float("inf")
    fetched_at = parcel.fetchedAt.timestamp() if parcel.fetchedAt else 0.0
    return (area_sqft, -fetched_at)
