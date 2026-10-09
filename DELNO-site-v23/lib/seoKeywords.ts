import { wordstatSeedQueue } from "./seoBlogCore";

/** Core queries for DELNO — synced with blog SEO seed queue (Wordstat). */
export const delnoSeoKeywords = [
  ...wordstatSeedQueue.slice(0, 12),
  "DELNO",
] as const;
