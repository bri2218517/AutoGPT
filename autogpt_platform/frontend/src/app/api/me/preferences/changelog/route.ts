import { NextResponse, type NextRequest } from "next/server";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
const UPSTREAM_PATH = "/api/me/preferences/changelog";

async function forward(req: NextRequest, body?: string) {
  const upstream = `${BACKEND_URL}${UPSTREAM_PATH}`;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  const cookie = req.headers.get("cookie");
  if (cookie) headers["cookie"] = cookie;
  const auth = req.headers.get("authorization");
  if (auth) headers["authorization"] = auth;

  const res = await fetch(upstream, {
    method: req.method,
    headers,
    body,
  });

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: {
      "Content-Type": res.headers.get("Content-Type") ?? "application/json",
    },
  });
}

export async function GET(req: NextRequest) {
  return forward(req);
}

export async function PUT(req: NextRequest) {
  const body = await req.text();
  return forward(req, body);
}
