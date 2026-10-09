import type { MetadataRoute } from "next";
import { blogPosts } from "@/lib/blogPosts";
import { getSiteUrl } from "@/lib/siteUrl";

export default function sitemap(): MetadataRoute.Sitemap {
  const site = getSiteUrl();
  const now = new Date();
  const staticPages = [
    "",
    "/v3",
    "/blog",
    "/help",
    "/privacy",
    "/terms",
  ];
  const blogPages = blogPosts.map((p) => `/blog/${p.slug}`);

  const pages = [...staticPages, ...blogPages];

  return pages.map((path) => ({
    url: `${site}${path}`,
    lastModified: now,
    changeFrequency: path === "" || path === "/blog" ? "weekly" : "monthly",
    priority: path === "" ? 1 : path === "/blog" ? 0.85 : 0.6,
  }));
}
