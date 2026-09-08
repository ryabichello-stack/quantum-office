export const runtime = "nodejs";

type CmsFaqResponse = {
  slug?: string;
  title?: string;
  blocks?: { sections?: Array<{ q?: string; a?: string }> };
  source?: string;
};

export async function GET() {
  const apiBase = (process.env.DELNO_API_URL || process.env.NEXT_PUBLIC_DELNO_API_URL || "").replace(
    /\/$/,
    "",
  );

  if (!apiBase) {
    return Response.json({ source: "fallback", reason: "DELNO_API_URL not set" }, { status: 503 });
  }

  try {
    const response = await fetch(`${apiBase}/v1/public/cms/pages/faq`, {
      headers: { Accept: "application/json" },
      next: { revalidate: 60 },
    });

    if (!response.ok) {
      return Response.json(
        { source: "fallback", reason: `cms_http_${response.status}` },
        { status: 502 },
      );
    }

    const data = (await response.json()) as CmsFaqResponse;
    const sections = data.blocks?.sections?.filter((s) => s.q && s.a) ?? [];
    if (!sections.length) {
      return Response.json({ source: "fallback", reason: "empty_cms_faq" }, { status: 502 });
    }

    return Response.json(
      { ...data, source: "cms" },
      {
        headers: {
          "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
        },
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "fetch_failed";
    return Response.json({ source: "fallback", reason: message }, { status: 502 });
  }
}
