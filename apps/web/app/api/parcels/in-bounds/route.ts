import { NextResponse } from "next/server";

const BACKEND_URL = process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const county = searchParams.get("county");
  const minLng = searchParams.get("minLng");
  const minLat = searchParams.get("minLat");
  const maxLng = searchParams.get("maxLng");
  const maxLat = searchParams.get("maxLat");
  const limit = searchParams.get("limit") ?? "150";

  if (!county || !minLng || !minLat || !maxLng || !maxLat) {
    return NextResponse.json(
      { error: "county, minLng, minLat, maxLng, and maxLat are required" },
      { status: 400 }
    );
  }

  const url =
    `${BACKEND_URL}/api/parcels/in-bounds?county=${encodeURIComponent(county)}` +
    `&minLng=${encodeURIComponent(minLng)}` +
    `&minLat=${encodeURIComponent(minLat)}` +
    `&maxLng=${encodeURIComponent(maxLng)}` +
    `&maxLat=${encodeURIComponent(maxLat)}` +
    `&limit=${encodeURIComponent(limit)}`;

  const response = await fetch(url, { cache: "no-store" });
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "content-type": "application/json" },
  });
}
