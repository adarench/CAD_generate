import { NextResponse } from "next/server";
import { fetchParcelById } from "@/app/api/parcels/_lib";

export async function GET(_request: Request, { params }: { params: { id: string } }) {
  const parcel = await fetchParcelById(params.id);
  if (!parcel) {
    return NextResponse.json({ error: "Parcel not found" }, { status: 404 });
  }
  return NextResponse.json(parcel);
}
