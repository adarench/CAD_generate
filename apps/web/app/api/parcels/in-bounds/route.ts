import { NextResponse } from "next/server";
import { fetchParcelsForBounds } from "@/app/api/parcels/_lib";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const county = searchParams.get("county");
  const minLng = Number(searchParams.get("minLng"));
  const minLat = Number(searchParams.get("minLat"));
  const maxLng = Number(searchParams.get("maxLng"));
  const maxLat = Number(searchParams.get("maxLat"));
  const limit = Number(searchParams.get("limit") ?? "2000");
  const zoom = Number(searchParams.get("zoom") ?? "0");

  if (!county || ![minLng, minLat, maxLng, maxLat].every((value) => Number.isFinite(value))) {
    return NextResponse.json(
      { error: "county, minLng, minLat, maxLng, and maxLat are required" },
      { status: 400 }
    );
  }

  const parcels = await fetchParcelsForBounds(
    county,
    { minLng, minLat, maxLng, maxLat },
    Number.isFinite(limit) ? limit : 2000,
    Number.isFinite(zoom) ? zoom : null
  );
  return NextResponse.json(parcels);
}
