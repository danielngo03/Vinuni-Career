import { NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const payload = await request.json();
  const response = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
