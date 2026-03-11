import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from schemas import (
    OptimizationRequest,
    OptimizationResponse,
    ParcelLookupResponse,
    ParcelRecord,
    RunDetail,
    RunSummary,
)
from services.optimization_service import OptimizerService
from services.parcel_service import ParcelService

app = FastAPI(title="Utah Subdivision API", version="0.2.0")
LOGGER = logging.getLogger(__name__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
service = OptimizerService()
parcel_service = ParcelService()
exports_dir = Path("apps/python-api/data/exports")
exports_dir.mkdir(parents=True, exist_ok=True)
app.mount("/exports", StaticFiles(directory=exports_dir), name="exports")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/optimize", response_model=OptimizationResponse)
async def optimize(request: OptimizationRequest):
    try:
        run = await service.optimize(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return service.response_only(run)


@app.get("/api/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: str):
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.get("/api/parcels/{parcel_id}/latest-run", response_model=RunDetail)
async def get_latest_run_for_parcel(parcel_id: str):
    run = await service.get_latest_run_for_parcel(parcel_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No saved runs found for parcel")
    return run


@app.get("/api/runs", response_model=list[RunSummary])
async def list_runs(limit: int = Query(default=10, ge=1, le=50)):
    return await service.list_runs(limit)


@app.get("/api/parcels/search", response_model=list[ParcelRecord])
async def parcel_search(county: str, apn: str):
    results = await parcel_service.search_by_apn(county, apn)
    if not results:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return results


@app.get("/api/parcels/by-click", response_model=ParcelLookupResponse)
async def parcel_by_click(lng: float, lat: float, county: str):
    results = await parcel_service.search_by_point(county, lng, lat)
    if not results:
        raise HTTPException(status_code=404, detail="No parcel found at that location")
    return ParcelLookupResponse(
        selected=results[0],
        candidates=results,
        message="Multiple parcel candidates were returned. The smallest parcel is selected by default."
        if len(results) > 1
        else None,
    )


@app.get("/api/parcels/recent", response_model=list[ParcelRecord])
async def recent_parcels(limit: int = Query(default=8, ge=1, le=20)):
    return await parcel_service.list_recent_parcels(limit)


@app.get("/api/parcels/in-bounds", response_model=list[ParcelRecord])
async def parcels_in_bounds(
    county: str,
    minLng: float,
    minLat: float,
    maxLng: float,
    maxLat: float,
    limit: int = Query(default=150, ge=1, le=5000),
    zoom: Optional[float] = Query(default=None, ge=0),
):
    try:
        parcels = await parcel_service.search_by_bounds(
            county=county,
            min_lng=minLng,
            min_lat=minLat,
            max_lng=maxLng,
            max_lat=maxLat,
            limit=limit,
            zoom=zoom,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    print(
        "[parcel-bounds]",
        {
            "county": county,
            "minLng": minLng,
            "minLat": minLat,
            "maxLng": maxLng,
            "maxLat": maxLat,
            "limit": limit,
            "zoom": zoom,
            "count": len(parcels),
        },
    )
    return parcels


@app.get("/api/parcels/{parcel_id}", response_model=ParcelRecord)
async def get_parcel(parcel_id: str):
    parcel = await parcel_service.get_parcel(parcel_id)
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    return parcel
