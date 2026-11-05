import { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  const id = request.nextUrl.searchParams.get("id") || "";
  if (!/^[A-Za-z0-9_-]{11}$/.test(id)) return new Response("Link YouTube không hợp lệ", { status: 400 });
  for (const size of ["maxresdefault", "hqdefault"]) {
    try {
      const response = await fetch(`https://i.ytimg.com/vi/${id}/${size}.jpg`, { signal: AbortSignal.timeout(8000) });
      if (!response.ok || !response.headers.get("content-type")?.startsWith("image/")) continue;
      return new Response(await response.arrayBuffer(), { headers: {
        "Content-Type": "image/jpeg",
        "Content-Disposition": `attachment; filename="youtube-${id}.jpg"`,
        "Cache-Control": "public, max-age=3600",
      } });
    } catch { /* Try the next thumbnail size. */ }
  }
  return new Response("Chưa tải được thumbnail. Vui lòng thử lại.", { status: 502 });
}
