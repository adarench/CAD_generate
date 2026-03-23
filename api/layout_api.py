from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from services.layout_models import LayoutResult, ParcelInput, ZoningInput
from services.layout_service import search_layout as search_layout_service

app = FastAPI(title="GIS Layout Search API", version="0.1.0")


class LayoutSearchRequest(BaseModel):
    parcel: ParcelInput
    zoning: ZoningInput
    max_candidates: int = 50


@app.post("/layout/search", response_model=LayoutResult)
def search_layout(request: LayoutSearchRequest) -> LayoutResult:
    return search_layout_service(request.parcel, request.zoning, max_candidates=request.max_candidates)
