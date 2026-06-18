import { NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function POST(request: Request) {
  const response = await fetch(`${API_URL}/registrations/partner`, {
    method: "POST",
    body: await request.formData(),
    cache: "no-store",
  });
  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/json",
    },
  });
}
