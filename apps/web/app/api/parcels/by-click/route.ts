import { NextResponse } from "next/server";

const BACKEND_URL = process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const lng = Number(searchParams.get("lng"));
  const lat = Number(searchParams.get("lat"));
  const county = searchParams.get("county");
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    return NextResponse.json({ error: "lng and lat are required" }, { status: 400 });
  }
  if (!county) {
    return NextResponse.json({ error: "county is required" }, { status: 400 });
  }
  const response = await fetch(
    `${BACKEND_URL}/api/parcels/by-click?county=${encodeURIComponent(county)}&lng=${lng}&lat=${lat}`,
    { cache: "no-store" }
  );
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "content-type": "application/json" },
  });
}
