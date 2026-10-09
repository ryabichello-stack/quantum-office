import type { ReactNode } from "react";
import { V17SiteFooter, V17SiteHeader } from "./SiteChrome";

type Props = {
  children: ReactNode;
  /** Extra classes on the outer `.delno-v17` shell (e.g. content pages). */
  className?: string;
};

/** Matches reference V17 DOM: header, page, footer inside one `.delno-v17` root. */
export function V17PageShell({ children, className }: Props) {
  const rootClass = className ? `delno-v17 ${className}` : "delno-v17";
  return (
    <main className={rootClass}>
      <V17SiteHeader />
      {children}
      <V17SiteFooter />
    </main>
  );
}
