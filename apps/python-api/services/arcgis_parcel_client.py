from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import shape

from schemas import ParcelRecord, ParcelSourceRecord
from services.parcel_adapter import geometry_area_sqft

LOGGER = logging.getLogger(__name__)

UGRC_BASE = "https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services"
DEMO_PARCEL_PATH = Path("apps/web/data/demoParcel.json")
COUNTY_OVERRIDES = {
    "salt lake": "SaltLake",
    "san juan": "SanJuan",
    "juab": "Juab",
}


class ArcGISParcelClient:
    def __init__(self, timeout: float = 20.0, allow_fallback: bool = True):
        self.timeout = timeout
        self.allow_fallback = allow_fallback

    async def search_by_apn(self, county: str, apn: str) -> list[ParcelRecord]:
        query_values = [apn.strip()]
        normalized = normalize_apn(apn)
        if normalized and normalized not in query_values:
            query_values.append(normalized)

        records: list[ParcelRecord] = []
        try:
            for value in query_values:
                where = f"PARCEL_ID = '{escape_sql(value)}' OR ACCOUNT_NUM = '{escape_sql(value)}'"
                payload = await self._query_features(county, where=where)
                records = self._normalize_response(payload, county)
                if records:
                    break
        except httpx.HTTPError as exc:
            LOGGER.exception("Parcel APN lookup failed", extra={"county": county, "apn": apn})
            if not self.allow_fallback:
                raise RuntimeError(f"Parcel source unavailable for {county} County.") from exc
        if records:
            return records
        return await self._maybe_fallback(county, apn=apn)

    async def search_by_point(self, county: str, lng: float, lat: float) -> list[ParcelRecord]:
        geometry = json.dumps(
            {
                "x": lng,
                "y": lat,
                "spatialReference": {"wkid": 4326},
            }
        )
        try:
            payload = await self._query_features(
                county,
                where="1=1",
                extra_params={
                    "geometry": geometry,
                    "geometryType": "esriGeometryPoint",
                    "spatialRel": "esriSpatialRelIntersects",
                    "inSR": "4326",
                    "orderByFields": "Shape__Area ASC",
                    "resultRecordCount": "3",
                },
            )
            records = self._normalize_response(payload, county)
        except httpx.HTTPError as exc:
            LOGGER.exception(
                "Parcel point lookup failed",
                extra={"county": county, "lng": lng, "lat": lat},
            )
            if not self.allow_fallback:
                raise RuntimeError(f"Parcel source unavailable for {county} County.") from exc
            records = []
        if records:
            return records
        return await self._maybe_fallback(county, lng=lng, lat=lat)

    async def search_by_bounds(
        self,
        county: str,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        limit: int = 150,
    ) -> list[ParcelRecord]:
        geometry = json.dumps(
            {
                "xmin": min_lng,
                "ymin": min_lat,
                "xmax": max_lng,
                "ymax": max_lat,
                "spatialReference": {"wkid": 4326},
            }
        )
        try:
            payload = await self._query_features(
                county,
                where="1=1",
                extra_params={
                    "geometry": geometry,
                    "geometryType": "esriGeometryEnvelope",
                    "spatialRel": "esriSpatialRelIntersects",
                    "inSR": "4326",
                    "resultRecordCount": str(limit),
                    "orderByFields": "Shape__Area ASC",
                },
            )
            records = self._normalize_response(payload, county)
            print(
                "[parcel-bounds-source]",
                {
                    "county": county,
                    "minLng": min_lng,
                    "minLat": min_lat,
                    "maxLng": max_lng,
                    "maxLat": max_lat,
                    "limit": limit,
                    "count": len(records),
                },
            )
            return records
        except httpx.HTTPError as exc:
            LOGGER.exception(
                "Parcel bounds lookup failed",
                extra={
                    "county": county,
                    "min_lng": min_lng,
                    "min_lat": min_lat,
                    "max_lng": max_lng,
                    "max_lat": max_lat,
                },
            )
            raise RuntimeError(f"Parcel source unavailable for {county} County.") from exc

    def parcel_source(self, county: str) -> ParcelSourceRecord:
        service_url = self._service_url(county)
        return ParcelSourceRecord(
            id=f"ugrc-{slugify_county(county)}",
            provider="UGRC ArcGIS REST",
            datasetName=f"Parcels_{slugify_county(county)}",
            datasetUrl=service_url,
            refreshStatus="active",
            metadataJson={
                "county": county,
                "queryLayer": f"{service_url}/query",
            },
        )

    async def _query_features(
        self,
        county: str,
        where: str,
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        service_url = self._service_url(county)
        params = {
            "f": "geojson",
            "where": where,
            "returnGeometry": "true",
            "outFields": ",".join(
                [
                    "OBJECTID",
                    "FIPS",
                    "PARCEL_ID",
                    "PARCEL_ADD",
                    "PARCEL_CITY",
                    "PARCEL_ZIP",
                    "OWN_TYPE",
                    "RECORDER",
                    "CoParcel_URL",
                    "ACCOUNT_NUM",
                    "Shape__Area",
                    "Shape__Length",
                    "ParcelsCur",
                ]
            ),
            "outSR": "4326",
        }
        if extra_params:
            params.update(extra_params)

        LOGGER.info("Querying parcel service", extra={"county": county, "service_url": service_url})
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(f"{service_url}/query", params=params)
            response.raise_for_status()
            return response.json()

    def _normalize_response(self, payload: dict[str, Any], county: str) -> list[ParcelRecord]:
        features = payload.get("features", [])
        records: list[ParcelRecord] = []
        for feature in features:
            geometry = feature.get("geometry")
            properties = feature.get("properties", {})
            if not geometry:
                continue
            shapely_geom = shape(geometry)
            centroid = shapely_geom.centroid
            area_sqft = round(geometry_area_sqft(geometry), 2)
            address = " ".join(
                part
                for part in [
                    string_or_none(properties.get("PARCEL_ADD")),
                    string_or_none(properties.get("PARCEL_CITY")),
                    string_or_none(properties.get("PARCEL_ZIP")),
                ]
                if part
            ).strip()
            apn = string_or_none(properties.get("PARCEL_ID")) or string_or_none(
                properties.get("ACCOUNT_NUM")
            )
            records.append(
                ParcelRecord(
                    id=f"ut-{slugify_county(county)}-{normalize_apn(apn) or properties.get('OBJECTID')}",
                    county=county,
                    apn=apn,
                    sourceProvider="UGRC ArcGIS REST",
                    sourceDataset=f"Parcels_{slugify_county(county)}",
                    sourceObjectId=string_or_none(properties.get("OBJECTID")),
                    geometryGeoJSON=geometry,
                    centroid={"lng": centroid.x, "lat": centroid.y},
                    areaSqft=area_sqft if area_sqft else None,
                    areaAcres=round(area_sqft / 43560.0, 4) if area_sqft else None,
                    address=address or None,
                    ownerName=None,
                    zoningCode=None,
                    landUse=string_or_none(properties.get("OWN_TYPE")),
                    rawAttributes={
                        **properties,
                        "county": county,
                        "serviceUrl": self._service_url(county),
                    },
                    fetchedAt=datetime.now(timezone.utc),
                )
            )
        return records

    async def _maybe_fallback(
        self,
        county: str,
        apn: str | None = None,
        lng: float | None = None,
        lat: float | None = None,
    ) -> list[ParcelRecord]:
        if not self.allow_fallback or not DEMO_PARCEL_PATH.exists():
            return []
        raw = json.loads(DEMO_PARCEL_PATH.read_text())
        if apn and normalize_apn(raw.get("apn")) != normalize_apn(apn):
            return []
        if county and county.lower() != raw.get("county", "").lower():
            return []
        LOGGER.warning("Using demo parcel fallback", extra={"county": county, "lng": lng, "lat": lat})
        return [
            ParcelRecord(
                id=raw["id"],
                county=raw["county"],
                apn=raw.get("apn"),
                sourceProvider="Local Demo Fallback",
                sourceDataset="demoParcel",
                sourceObjectId=raw.get("sourceObjectId"),
                geometryGeoJSON=raw["geometry"],
                centroid=raw["centroid"] if "centroid" in raw else estimate_centroid(raw["geometry"]),
                areaSqft=raw.get("areaSqft"),
                areaAcres=raw.get("areaAcres"),
                address=raw.get("address"),
                ownerName=raw.get("ownerName"),
                zoningCode=raw.get("zoningCode"),
                landUse=raw.get("landUse"),
                rawAttributes=raw.get("rawAttributes", {}),
                fetchedAt=datetime.now(timezone.utc),
            )
        ]

    def _service_url(self, county: str) -> str:
        slug = slugify_county(county)
        return f"{UGRC_BASE}/Parcels_{slug}/FeatureServer/0"


def slugify_county(county: str) -> str:
    key = county.strip().lower()
    if key in COUNTY_OVERRIDES:
        return COUNTY_OVERRIDES[key]
    return re.sub(r"[^A-Za-z0-9]", "", county.title())


def normalize_apn(value: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value or "")


def escape_sql(value: str) -> str:
    return value.replace("'", "''")


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def estimate_centroid(geometry: dict[str, Any]) -> dict[str, float]:
    shapely_geom = shape(geometry)
    centroid = shapely_geom.centroid
    return {"lng": centroid.x, "lat": centroid.y}
