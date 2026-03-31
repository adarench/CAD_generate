import { NextRequest, NextResponse } from "next/server";

const BEDROCK_URL = process.env.BEDROCK_API_URL ?? process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: NextRequest) {
  const search = request.nextUrl.searchParams.toString();
  const url = `${BEDROCK_URL}/optimization/runs${search ? `?${search}` : ""}`;
  const response = await fetch(url, { cache: "no-store" });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
