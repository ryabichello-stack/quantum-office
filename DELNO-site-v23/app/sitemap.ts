import type { MetadataRoute } from "next";
import { blogPosts } from "@/lib/blogPosts";
import { getSiteUrl } from "@/lib/siteUrl";

export default function sitemap(): MetadataRoute.Sitemap {
  const site = getSiteUrl();
  const staticPages = [
    "",
    "/blog",
    "/help",
    "/solutions/booking",
    "/solutions/salon",
    "/privacy",
    "/terms",
  ];
  const staticEntries: MetadataRoute.Sitemap = staticPages.map((path) => ({
    url: `${site}${path}`,
  }));
  const blogEntries: MetadataRoute.Sitemap = blogPosts.map((post) => ({
    url: `${site}/blog/${post.slug}`,
    lastModified: new Date(`${post.publishedAt}T00:00:00Z`),
  }));

  return [...staticEntries, ...blogEntries];
}
