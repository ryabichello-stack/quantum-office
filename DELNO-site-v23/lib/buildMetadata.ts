import type { Metadata } from "next";
import { delnoSeoKeywords } from "./seoKeywords";
import { getSiteUrl } from "./siteUrl";

type SeoInput = {
  title: string;
  description: string;
  path?: string;
  keywords?: string[];
};

export function buildDelnoMetadata(input: SeoInput): Metadata {
  const site = getSiteUrl();
  const path = input.path?.startsWith("/") ? input.path : input.path ? `/${input.path}` : "";
  const url = `${site}${path}`;
  const keywords = input.keywords ?? [...delnoSeoKeywords];
  const verification = process.env.NEXT_PUBLIC_YANDEX_VERIFICATION?.trim();

  return {
    metadataBase: new URL(site),
    title: input.title,
    description: input.description,
    keywords,
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      locale: "ru_RU",
      url,
      siteName: "DELNO",
      title: input.title,
      description: input.description,
    },
    twitter: {
      card: "summary_large_image",
      title: input.title,
      description: input.description,
    },
    robots: { index: true, follow: true },
    ...(verification
      ? {
          verification: {
            yandex: verification,
          },
        }
      : {}),
  };
}
