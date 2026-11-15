import ConvertLanding from "./v2/ConvertLanding";
import { heroHeadline } from "./v2/v17/V17Landing";

import "./v2/dv17.bundle.css";
import "./v2/v17-overrides.css";

type HomeProps = {
  searchParams: Promise<{ h?: string | string[] }>;
};

/** Canonical marketing landing — V17 (former `/v2`). */
export default async function DelnoHome({ searchParams }: HomeProps) {
  const { h } = await searchParams;
  return <ConvertLanding headline={heroHeadline(h)} />;
}
