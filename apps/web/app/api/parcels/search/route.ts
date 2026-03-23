import { NextResponse } from "next/server";
import { searchParcelsByApn } from "@/app/api/parcels/_lib";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const county = searchParams.get("county");
  const apn = searchParams.get("apn");
  if (!county || !apn) {
    return NextResponse.json({ error: "county and apn are required" }, { status: 400 });
  }
  const parcels = await searchParcelsByApn(county, apn);
  return NextResponse.json(parcels);
}
