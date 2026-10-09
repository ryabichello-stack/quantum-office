import type { MetadataRoute } from "next";
import { getSiteUrl } from "@/lib/siteUrl";

export default function sitemap(): MetadataRoute.Sitemap {
  const site = getSiteUrl();
  const now = new Date();
  const pages = [
    "",
    "/v2",
    "/v2/blog",
    "/v2/help",
    "/v2/blog/one-employee-many-channels",
    "/v2/blog/prepare-knowledge-base",
    "/privacy",
    "/terms",
  ];
  return pages.map((path, i) => ({
    url: `${site}${path}`,
    lastModified: now,
    changeFrequency: path === "" || path === "/v2" ? "weekly" : "monthly",
    priority: path === "" ? 1 : path === "/v2" ? 0.95 : 0.6,
  }));
}
