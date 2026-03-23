import { NextResponse } from "next/server";

const BEDROCK_URL = process.env.BEDROCK_API_URL ?? process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const query = url.searchParams.toString();
  const response = await fetch(`${BEDROCK_URL}/runs${query ? `?${query}` : ""}`, {
    cache: "no-store",
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
