import { NextResponse } from "next/server";

const BEDROCK_URL = process.env.BEDROCK_API_URL ?? process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(_request: Request, { params }: { params: { id: string } }) {
  const response = await fetch(`${BEDROCK_URL}/decisions/${params.id}`, { cache: "no-store" });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}

export async function PATCH(request: Request, { params }: { params: { id: string } }) {
  const body = await request.text();
  const response = await fetch(`${BEDROCK_URL}/decisions/${params.id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body,
    cache: "no-store",
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
