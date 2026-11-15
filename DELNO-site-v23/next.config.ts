import type { NextConfig } from "next";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH?.trim() ?? "";

const nextConfig: NextConfig = {
  ...(basePath ? { basePath } : {}),
  async redirects() {
    return [
      { source: "/v2/blog/:slug", destination: "/blog/:slug", permanent: true },
      { source: "/v2/blog", destination: "/blog", permanent: true },
      { source: "/v2/help", destination: "/help", permanent: true },
      { source: "/v2", destination: "/", permanent: true },
      { source: "/v3", destination: "/", permanent: true },
      { source: "/v4", destination: "/", permanent: true },
    ];
  },
};

export default nextConfig;
