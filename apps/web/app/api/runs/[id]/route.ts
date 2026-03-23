import { NextResponse } from "next/server";

const BEDROCK_URL = process.env.BEDROCK_API_URL ?? process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";

export async function GET(_: Request, context: { params: { id: string } }) {
  const response = await fetch(`${BEDROCK_URL}/runs/${context.params.id}`, {
    cache: "no-store",
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
