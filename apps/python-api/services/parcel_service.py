from __future__ import annotations

import logging
from time import perf_counter

from schemas import ParcelRecord
from services.arcgis_parcel_client import ArcGISParcelClient
from services.persistence import PersistenceLayer

LOGGER = logging.getLogger(__name__)


class ParcelService:
    def __init__(self):
        self.persistence = PersistenceLayer()
        self.arcgis = ArcGISParcelClient()

    async def get_parcel(self, parcel_id: str) -> ParcelRecord | None:
        return await self.persistence.get_parcel(parcel_id)

    async def list_recent_parcels(self, limit: int = 8) -> list[ParcelRecord]:
        return await self.persistence.list_recent_parcels(limit)

    async def search_by_bounds(
        self,
        county: str,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        limit: int = 150,
        zoom: float | None = None,
    ) -> list[ParcelRecord]:
        started_at = perf_counter()
        cached = await self.persistence.search_parcels_by_bounds(
            county=county,
            min_lng=min_lng,
            min_lat=min_lat,
            max_lng=max_lng,
            max_lat=max_lat,
            limit=limit,
            zoom=zoom,
        )
        if self.persistence.database_enabled and cached:
            self._log_query("postgis", county, len(cached), started_at, limit, zoom)
            return cached
        try:
            live = await self.arcgis.search_by_bounds(
                county=county,
                min_lng=min_lng,
                min_lat=min_lat,
                max_lng=max_lng,
                max_lat=max_lat,
                limit=limit,
            )
        except RuntimeError:
            local_fallback = self.persistence.search_local_parcels_by_bounds(
                county=county,
                min_lng=min_lng,
                min_lat=min_lat,
                max_lng=max_lng,
                max_lat=max_lat,
                limit=limit,
            )
            if local_fallback:
                LOGGER.warning(
                    "Serving JSON parcel bounds after live lookup failed",
                    extra={
                        "county": county,
                        "min_lng": min_lng,
                        "min_lat": min_lat,
                        "max_lng": max_lng,
                        "max_lat": max_lat,
                        "cached_count": len(local_fallback),
                    },
                )
                self._log_query("json_fallback", county, len(local_fallback), started_at, limit, zoom)
                return local_fallback
            if cached:
                LOGGER.warning(
                    "Serving cached parcel bounds after live lookup failed",
                    extra={
                        "county": county,
                        "min_lng": min_lng,
                        "min_lat": min_lat,
                        "max_lng": max_lng,
                        "max_lat": max_lat,
                        "cached_count": len(cached),
                    },
                )
                self._log_query("postgis_fallback", county, len(cached), started_at, limit, zoom)
                return cached
            raise
        if live:
            await self._cache_records(live, county)
            self._log_query("arcgis_fallback", county, len(live), started_at, limit, zoom)
            return live
        if cached:
            LOGGER.info(
                "Serving cached parcel bounds because live lookup returned no records",
                extra={
                    "county": county,
                    "min_lng": min_lng,
                    "min_lat": min_lat,
                    "max_lng": max_lng,
                    "max_lat": max_lat,
                    "cached_count": len(cached),
                },
            )
            self._log_query("postgis_stale", county, len(cached), started_at, limit, zoom)
            return cached
        local_fallback = self.persistence.search_local_parcels_by_bounds(
            county=county,
            min_lng=min_lng,
            min_lat=min_lat,
            max_lng=max_lng,
            max_lat=max_lat,
            limit=limit,
        )
        if local_fallback:
            LOGGER.info(
                "Serving JSON parcel bounds because live lookup returned no records",
                extra={
                    "county": county,
                    "min_lng": min_lng,
                    "min_lat": min_lat,
                    "max_lng": max_lng,
                    "max_lat": max_lat,
                    "cached_count": len(local_fallback),
                },
            )
            self._log_query("json_fallback", county, len(local_fallback), started_at, limit, zoom)
            return local_fallback
        return []

    async def search_by_apn(self, county: str, apn: str) -> list[ParcelRecord]:
        cached = await self.persistence.search_parcels_by_apn(county, apn)
        if cached:
            return cached
        live = await self.arcgis.search_by_apn(county, apn)
        if live:
            await self._cache_records(live, county)
            return live
        return self.persistence.search_local_parcels_by_apn(county, apn)

    async def search_by_point(self, county: str, lng: float, lat: float) -> list[ParcelRecord]:
        cached = await self.persistence.search_parcels_by_point(county, lng, lat)
        if self.persistence.database_enabled and cached:
            LOGGER.info(
                "Serving parcel point lookup from PostGIS cache",
                extra={"county": county, "lng": lng, "lat": lat, "count": len(cached)},
            )
            return cached
        live = await self.arcgis.search_by_point(county, lng, lat)
        if live:
            await self._cache_records(live, county)
            return live
        if cached:
            LOGGER.warning(
                "Serving cached parcel point lookup after live lookup returned no records",
                extra={"county": county, "lng": lng, "lat": lat, "cached_count": len(cached)},
            )
            return cached
        return self.persistence.search_local_parcels_by_point(county, lng, lat)

    async def ensure_cached(self, parcel: ParcelRecord) -> ParcelRecord:
        await self.persistence.save_parcel(parcel, source=self.arcgis.parcel_source(parcel.county))
        return parcel

    async def _cache_records(self, records: list[ParcelRecord], county: str) -> None:
        source = self.arcgis.parcel_source(county)
        await self.persistence.save_parcel_batch(records, source=source, update_json=True)

    def _log_query(
        self,
        source: str,
        county: str,
        rows: int,
        started_at: float,
        limit: int,
        zoom: float | None,
    ) -> None:
        query_time_ms = round((perf_counter() - started_at) * 1000, 2)
        LOGGER.info(
            "[parcel_service] source=%s county=%s rows=%s query_time=%sms limit=%s zoom=%s",
            source,
            county,
            rows,
            query_time_ms,
            limit,
            zoom,
        )
