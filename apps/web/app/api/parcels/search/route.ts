import { NextResponse } from "next/server";

const BACKEND_URL = process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const county = searchParams.get("county");
  const apn = searchParams.get("apn");
  if (!county || !apn) {
    return NextResponse.json({ error: "county and apn are required" }, { status: 400 });
  }
  const response = await fetch(
    `${BACKEND_URL}/api/parcels/search?county=${encodeURIComponent(county)}&apn=${encodeURIComponent(apn)}`,
    { cache: "no-store" }
  );
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "content-type": "application/json" },
  });
}
