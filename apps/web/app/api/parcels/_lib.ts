import { COUNTY_DEFAULT_VIEWS, DEFAULT_MAP_COUNTY, DEFAULT_MAP_VIEW } from "@/lib/mapConfig";
import { countyServiceUrl, SUPPORTED_UTAH_COUNTIES } from "@/services/parcels/arcgisParcelClient";
import { normalizeParcel, type ParcelRecord } from "@/services/parcels/parcelNormalizer";

type Bounds = {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
};

type ParcelLookupResponse = {
  selected: ParcelRecord | null;
  candidates: ParcelRecord[];
  message?: string | null;
};

type ArcgisFeature = {
  attributes?: Record<string, unknown>;
  geometry?: {
    rings?: number[][][];
  };
};

const FIELD_NAME_CANDIDATES = {
  objectId: ["OBJECTID", "OBJECTID_1", "OID", "FID"],
  apn: ["PARCEL_ID", "PARCELID", "PARCEL_ID1", "APN", "PARCEL_NO", "SERIAL", "PIN", "ACCOUNTNO"],
  address: ["SITE_ADDR", "SITUSADDR", "ADDRESS", "ADDR_FULL", "PROPADDR"],
  owner: ["OWNER", "OWNER_NAME", "OWNERNME1", "PRIMARY_OWN"],
  zoning: ["ZONE", "ZONING", "ZONING_CODE", "ZONE_CODE"],
  landUse: ["LANDUSE", "LAND_USE", "PROP_CLASS", "USE_CODE"],
} as const;

const countyBySlug = new Map(SUPPORTED_UTAH_COUNTIES.map((county) => [slugifyCounty(county), county]));
const fieldCache = new Map<string, Promise<string[]>>();

export async function fetchParcelsForBounds(
  county: string,
  bounds: Bounds,
  limit: number,
  zoom?: number | null
): Promise<ParcelRecord[]> {
  try {
    const features = await queryArcgis(county, {
      where: "1=1",
      geometry: `${bounds.minLng},${bounds.minLat},${bounds.maxLng},${bounds.maxLat}`,
      geometryType: "esriGeometryEnvelope",
      spatialRel: "esriSpatialRelIntersects",
      resultRecordCount: String(Math.max(50, Math.min(limit, 4000))),
    });
    const parcels = features
      .map((feature) => toParcelRecord(feature, county))
      .filter((parcel): parcel is ParcelRecord => Boolean(parcel));
    if (parcels.length) {
      return parcels;
    }
  } catch {
    return [];
  }
  return [];
}

export async function fetchParcelByClick(
  county: string,
  lng: number,
  lat: number,
  zoom?: number | null
): Promise<ParcelLookupResponse> {
  try {
    const pointHits = await queryArcgis(county, {
      where: "1=1",
      geometry: `${lng},${lat}`,
      geometryType: "esriGeometryPoint",
      spatialRel: "esriSpatialRelIntersects",
      resultRecordCount: "12",
    });
    const candidates = pointHits
      .map((feature) => toParcelRecord(feature, county))
      .filter((parcel): parcel is ParcelRecord => Boolean(parcel));
    if (candidates.length) {
      return {
        selected: candidates[0],
        candidates,
        message: `Selected ${candidates.length} parcel${candidates.length === 1 ? "" : "s"} from the live parcel layer.`,
      };
    }
  } catch {
    return {
      selected: null,
      candidates: [],
      message: "No live parcel found at that location.",
    };
  }
  return {
    selected: null,
    candidates: [],
    message: "No live parcel found at that location.",
  };
}

export async function searchParcelsByApn(county: string, apn: string): Promise<ParcelRecord[]> {
  const trimmed = apn.trim();
  if (!trimmed) return [];
  try {
    const fields = await fetchServiceFields(county);
    const apnField = FIELD_NAME_CANDIDATES.apn.find((candidate) => fields.includes(candidate));
    if (apnField) {
      const safe = trimmed.replace(/'/g, "''").toUpperCase();
      const features = await queryArcgis(county, {
        where: `UPPER(${apnField}) LIKE '%${safe}%'`,
        resultRecordCount: "12",
      });
      const parcels = features
        .map((feature) => toParcelRecord(feature, county))
        .filter((parcel): parcel is ParcelRecord => Boolean(parcel));
      if (parcels.length) return parcels;
    }
  } catch {
    return [];
  }
  return [];
}

export async function fetchParcelById(id: string): Promise<ParcelRecord | null> {
  const parsed = parseArcgisParcelId(id);
  if (!parsed) return null;

  try {
    const features = await queryArcgis(parsed.county, {
      where: `${parsed.objectIdField} = ${parsed.objectId}`,
      resultRecordCount: "1",
    });
    const match = features
      .map((feature) => toParcelRecord(feature, parsed.county))
      .find((parcel): parcel is ParcelRecord => Boolean(parcel));
    return match ?? null;
  } catch {
    return null;
  }
}

export async function fetchRecentParcels(limit: number): Promise<ParcelRecord[]> {
  const county = DEFAULT_MAP_COUNTY || "Salt Lake";
  const center = COUNTY_DEFAULT_VIEWS[county] ?? DEFAULT_MAP_VIEW;
  return fetchParcelsForBounds(
    county,
    {
      minLng: center.lng - 0.02,
      minLat: center.lat - 0.015,
      maxLng: center.lng + 0.02,
      maxLat: center.lat + 0.015,
    },
    Math.max(4, Math.min(limit, 24)),
    center.zoom
  );
}

async function queryArcgis(county: string, params: Record<string, string>): Promise<ArcgisFeature[]> {
  const url = new URL(`${countyServiceUrl(county)}/query`);
  url.searchParams.set("f", "json");
  url.searchParams.set("returnGeometry", "true");
  url.searchParams.set("outFields", "*");
  url.searchParams.set("outSR", "4326");
  url.searchParams.set("inSR", "4326");
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }

  const response = await fetch(url.toString(), { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`ArcGIS parcel query failed for ${county} (${response.status}).`);
  }
  const payload = (await response.json()) as {
    error?: { message?: string };
    features?: ArcgisFeature[];
  };
  if (payload.error) {
    throw new Error(payload.error.message ?? `ArcGIS parcel query failed for ${county}.`);
  }
  return payload.features ?? [];
}

async function fetchServiceFields(county: string): Promise<string[]> {
  const key = slugifyCounty(county);
  const existing = fieldCache.get(key);
  if (existing) return existing;
  const pending = (async () => {
    const response = await fetch(`${countyServiceUrl(county)}?f=json`, { cache: "force-cache" });
    if (!response.ok) {
      throw new Error(`Failed to load service metadata for ${county}.`);
    }
    const payload = (await response.json()) as { fields?: Array<{ name?: string }> };
    return (payload.fields ?? []).map((field) => field.name ?? "").filter(Boolean);
  })();
  fieldCache.set(key, pending);
  return pending;
}

function toParcelRecord(feature: ArcgisFeature, county: string): ParcelRecord | null {
  const attrs = feature.attributes ?? {};
  const geometry = esriRingsToGeoJson(feature.geometry?.rings);
  if (!geometry) return null;

  const objectIdField = FIELD_NAME_CANDIDATES.objectId.find((candidate) => candidate in attrs);
  const objectId = objectIdField ? attrs[objectIdField] : null;
  const apn = firstString(attrs, FIELD_NAME_CANDIDATES.apn);
  const id =
    objectId !== null && objectId !== undefined
      ? `ut-${slugifyCounty(county)}-${String(objectId)}`
      : `ut-${slugifyCounty(county)}-${slugifyValue(apn ?? "parcel")}`;

  return normalizeParcel({
    id,
    county,
    apn,
    geometry,
    sourceProvider: "Utah ArcGIS",
    sourceDataset: `Parcels ${county}`,
    sourceObjectId: objectId !== null && objectId !== undefined ? String(objectId) : null,
    address: firstString(attrs, FIELD_NAME_CANDIDATES.address),
    ownerName: firstString(attrs, FIELD_NAME_CANDIDATES.owner),
    zoningCode: firstString(attrs, FIELD_NAME_CANDIDATES.zoning),
    landUse: firstString(attrs, FIELD_NAME_CANDIDATES.landUse),
    rawAttributes: attrs,
  });
}

function firstString(record: Record<string, unknown>, candidates: readonly string[]) {
  for (const key of candidates) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number") return String(value);
  }
  return null;
}

function esriRingsToGeoJson(rings: number[][][] | undefined): GeoJSON.Polygon | null {
  if (!rings?.length) return null;
  return {
    type: "Polygon",
    coordinates: rings.map((ring) => closeRing(ring)),
  };
}

function closeRing(ring: number[][]) {
  if (!ring.length) return ring;
  const [firstLng, firstLat] = ring[0];
  const [lastLng, lastLat] = ring[ring.length - 1];
  if (firstLng === lastLng && firstLat === lastLat) return ring;
  return [...ring, [firstLng, firstLat]];
}

function parseArcgisParcelId(id: string) {
  const match = /^ut-([a-z0-9-]+)-(\d+)$/.exec(id);
  if (!match) return null;
  const county = countyBySlug.get(match[1]);
  if (!county) return null;
  return {
    county,
    objectIdField: "OBJECTID",
    objectId: Number(match[2]),
  };
}

function slugifyCounty(county: string) {
  return county.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

function slugifyValue(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "parcel";
}
