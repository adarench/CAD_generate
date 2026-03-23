import { NextResponse } from "next/server";
import { fetchRecentParcels } from "@/app/api/parcels/_lib";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const limit = Number(url.searchParams.get("limit") ?? "8");
  const parcels = await fetchRecentParcels(Number.isFinite(limit) ? limit : 8);
  return NextResponse.json(parcels);
}
