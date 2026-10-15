const API_URL = process.env.API_URL ?? "http://localhost:8000";

// Same-origin proxy for the browser's saved and recent places (a list of region IDs).
export async function GET(req: Request) {
  const ids = new URL(req.url).searchParams.get("ids") ?? "";
  if (!/^\d+(,\d+){0,49}$/.test(ids)) return Response.json([]);
  const res = await fetch(`${API_URL}/api/v1/regions?ids=${ids}`, { next: { revalidate: 3600 } });
  return Response.json(res.ok ? await res.json() : [], { status: res.ok ? 200 : 502 });
}
