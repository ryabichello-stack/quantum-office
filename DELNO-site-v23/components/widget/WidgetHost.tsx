"use client";

import dynamic from "next/dynamic";

export const WidgetHost = dynamic(
  () => import("./CrystalWidget").then((m) => ({ default: m.CrystalWidget })),
  { ssr: false },
);
