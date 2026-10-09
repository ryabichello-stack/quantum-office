import { getSiteUrl } from "@/lib/siteUrl";

type Props = {
  /** Override for nested routes (e.g. /v2). */
  path?: string;
};

export function SeoJsonLd({ path = "" }: Props) {
  const site = getSiteUrl();
  const url = `${site}${path.startsWith("/") ? path : path ? `/${path}` : ""}`;

  const org = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "DELNO",
    url: site,
    email: "office@dlno.ru",
    logo: `${site}/delno-mark.svg`,
  };

  const app = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "DELNO",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    url,
    description:
      "ИИ-сотрудник: принимает звонки и сообщения, отвечает по базе знаний, записывает клиентов — 24/7.",
    offers: {
      "@type": "Offer",
      price: "2990",
      priceCurrency: "RUB",
      description: "Тариф «Диалоги» от 2 990 ₽/мес.",
    },
  };

  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Что такое DELNO?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "DELNO — ИИ-сотрудник для звонков, мессенджеров и почты: консультирует по вашим материалам и записывает клиентов.",
        },
      },
      {
        "@type": "Question",
        name: "Сколько стоит DELNO?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Тариф «Диалоги» — от 2 990 ₽ в месяц, «Диалоги + звонки» — от 5 990 ₽ в месяц.",
        },
      },
    ],
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(org) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(app) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faq) }} />
    </>
  );
}
