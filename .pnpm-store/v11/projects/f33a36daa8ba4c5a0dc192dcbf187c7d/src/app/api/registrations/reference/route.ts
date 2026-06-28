import { NextResponse } from "next/server";

const API_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000/api/v1";

export async function GET(request: Request) {
  const search = new URL(request.url).search;
  const response = await fetch(
    `${API_URL}/organizations/registration-reference${search}`,
    { cache: "no-store" },
  );
  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/json",
    },
  });
}
