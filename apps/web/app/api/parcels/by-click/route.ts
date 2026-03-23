import { NextResponse } from "next/server";
import { fetchParcelByClick } from "@/app/api/parcels/_lib";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const lng = Number(searchParams.get("lng"));
  const lat = Number(searchParams.get("lat"));
  const county = searchParams.get("county");
  const zoom = Number(searchParams.get("zoom") ?? "0");
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    return NextResponse.json({ error: "lng and lat are required" }, { status: 400 });
  }
  if (!county) {
    return NextResponse.json({ error: "county is required" }, { status: 400 });
  }
  const result = await fetchParcelByClick(county, lng, lat, Number.isFinite(zoom) ? zoom : null);
  return NextResponse.json(result);
}
