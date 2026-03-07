import { NextResponse } from "next/server";

const BACKEND_URL = process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(_: Request, context: { params: { id: string } }) {
  const response = await fetch(`${BACKEND_URL}/api/runs/${context.params.id}`, {
    cache: "no-store",
  });
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "content-type": "application/json" },
  });
}
