from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TopologyEnum(str, Enum):
    parallel = "parallel"
    spine = "spine"
    loop = "loop"
    culdesac = "culdesac"
    all = "all"


class ParcelGeometry(BaseModel):
    type: Literal["Polygon", "MultiPolygon"]
    coordinates: List[Any]


class ParcelRecord(BaseModel):
    id: str
    state: Literal["UT"] = "UT"
    county: str
    apn: Optional[str] = None
    sourceProvider: str
    sourceDataset: str
    sourceObjectId: Optional[str] = None
    geometryGeoJSON: ParcelGeometry
    centroid: dict[str, float]
    areaSqft: Optional[float] = None
    areaAcres: Optional[float] = None
    address: Optional[str] = None
    ownerName: Optional[str] = None
    zoningCode: Optional[str] = None
    landUse: Optional[str] = None
    rawAttributes: dict[str, Any] = Field(default_factory=dict)
    fetchedAt: datetime


class OptimizationParcelPayload(BaseModel):
    id: str
    state: Literal["UT"] = "UT"
    county: str
    apn: Optional[str] = None
    geometry: ParcelGeometry
    centroid: dict[str, float]
    areaSqft: Optional[float] = None
    areaAcres: Optional[float] = None
    address: Optional[str] = None
    ownerName: Optional[str] = None
    sourceProvider: str
    sourceDataset: str
    sourceObjectId: Optional[str] = None
    rawAttributes: dict[str, Any] = Field(default_factory=dict)
    fetchedAt: datetime


class ConceptInstruction(BaseModel):
    topologyPreferences: List[TopologyEnum] = Field(default_factory=list)
    excludedTopologies: List[TopologyEnum] = Field(default_factory=list)
    topologyMode: Literal["prefer", "strict"] = "prefer"
    densityIntent: Optional[Literal["maximize", "moderate", "low"]] = None
    roadIntent: Optional[str] = None
    lotIntent: Optional[str] = None
    edgeConditions: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class OptimizationRequest(BaseModel):
    parcelId: Optional[str] = None
    parcel: Optional[OptimizationParcelPayload] = None
    designConstraints: dict[str, Any] = Field(default_factory=dict)
    topologyPreferences: List[TopologyEnum] = Field(default_factory=lambda: [TopologyEnum.all])
    strictTopology: bool = False
    conceptText: Optional[str] = None

    @model_validator(mode="after")
    def validate_parcel_input(self) -> "OptimizationRequest":
        if not self.parcelId and not self.parcel:
            raise ValueError("Either parcelId or parcel must be provided.")
        return self


class TopologySummary(BaseModel):
    topology: str
    candidatesTested: int = 0
    lots: int
    roadLength: float
    developableAreaSqft: float = 0
    status: str
    notes: Optional[str] = None


class OptimizationResponse(BaseModel):
    runId: str
    winningTopology: str
    lotCount: int
    parcelAreaSqft: float
    roadLengthFt: float
    developableAreaSqft: float
    averageLotAreaSqft: float
    candidateSummary: List[TopologySummary]
    resolvedConstraints: dict[str, Any] = Field(default_factory=dict)
    conceptSummary: Optional[str] = None
    appliedInstruction: Optional[ConceptInstruction] = None
    resultGeoJSON: dict[str, Any]
    exports: dict[str, str]


class RunStatus(str, Enum):
    completed = "completed"
    failed = "failed"


class RunSummary(BaseModel):
    runId: str
    parcelId: str
    parcelApn: Optional[str] = None
    county: Optional[str] = None
    winningTopology: str
    lotCount: int
    createdAt: datetime
    status: RunStatus


class RunDetail(BaseModel):
    runId: str
    parcelId: str
    status: RunStatus
    parcel: Optional[ParcelRecord] = None
    inputConstraints: dict[str, Any] = Field(default_factory=dict)
    topologyPreferences: List[str] = Field(default_factory=list)
    strictTopology: bool = False
    createdAt: datetime
    response: OptimizationResponse


class ParcelSourceRecord(BaseModel):
    id: str
    provider: str
    datasetName: str
    datasetUrl: str
    refreshStatus: str = "active"
    metadataJson: dict[str, Any] = Field(default_factory=dict)


class ParcelSearchParams(BaseModel):
    county: str
    apn: str


class ParcelClickParams(BaseModel):
    lng: float
    lat: float
    county: Optional[str] = None


class ParcelLookupResponse(BaseModel):
    selected: Optional[ParcelRecord] = None
    candidates: List[ParcelRecord] = Field(default_factory=list)
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Layout Engine schemas
# ---------------------------------------------------------------------------

class LayoutGenerateRequest(BaseModel):
    parcel: OptimizationParcelPayload
    nCandidates: int = Field(default=24, ge=4, le=60)
    nTop: int = Field(default=3, ge=1, le=10)
    seed: int = Field(default=0, ge=0)
    roadWidthFt: float = Field(default=32.0, ge=16.0, le=80.0)
    lotDepthFt: float = Field(default=110.0, ge=50.0, le=250.0)
    minFrontageFt: float = Field(default=50.0, ge=25.0, le=150.0)
    usePrior: bool = True


class LayoutResultSummary(BaseModel):
    rank: int
    generatorType: str
    score: float
    lotCount: int
    totalRoadFt: float
    totalLotAreaSqft: float
    avgLotAreaSqft: float
    devAreaRatio: float


class LayoutGenerateResponse(BaseModel):
    parcelId: str
    areaAcres: float
    results: List[LayoutResultSummary]
    topResultGeoJSON: dict[str, Any]
    priorUsed: bool
