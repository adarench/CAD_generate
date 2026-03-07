from __future__ import annotations

from schemas import ParcelRecord
from services.arcgis_parcel_client import ArcGISParcelClient
from services.persistence import PersistenceLayer


class ParcelService:
    def __init__(self):
        self.persistence = PersistenceLayer()
        self.arcgis = ArcGISParcelClient()

    async def get_parcel(self, parcel_id: str) -> ParcelRecord | None:
        return await self.persistence.get_parcel(parcel_id)

    async def list_recent_parcels(self, limit: int = 8) -> list[ParcelRecord]:
        return await self.persistence.list_recent_parcels(limit)

    async def search_by_apn(self, county: str, apn: str) -> list[ParcelRecord]:
        cached = await self.persistence.search_parcels_by_apn(county, apn)
        if cached:
            return cached
        live = await self.arcgis.search_by_apn(county, apn)
        if live:
            await self._cache_records(live, county)
        return live

    async def search_by_point(self, county: str, lng: float, lat: float) -> list[ParcelRecord]:
        live = await self.arcgis.search_by_point(county, lng, lat)
        if not live:
            return []
        await self._cache_records(live, county)
        return live

    async def ensure_cached(self, parcel: ParcelRecord) -> ParcelRecord:
        await self.persistence.save_parcel(parcel, source=self.arcgis.parcel_source(parcel.county))
        return parcel

    async def _cache_records(self, records: list[ParcelRecord], county: str) -> None:
        source = self.arcgis.parcel_source(county)
        for record in records:
            await self.persistence.save_parcel(record, source=source)
