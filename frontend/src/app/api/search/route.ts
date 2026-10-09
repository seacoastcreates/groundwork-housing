const API_URL = process.env.API_URL ?? "http://localhost:8000";

// Same-origin proxy so the browser never needs the API's address or CORS.
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams.get("q") ?? "";
  if (q.trim().length < 2) return Response.json([]);
  const res = await fetch(`${API_URL}/api/v1/search?q=${encodeURIComponent(q)}`, { cache: "no-store" });
  return Response.json(res.ok ? await res.json() : [], { status: res.ok ? 200 : 502 });
}
