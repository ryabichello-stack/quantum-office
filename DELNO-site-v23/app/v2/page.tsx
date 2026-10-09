import { redirect } from "next/navigation";

export { DelnoPage } from "./DelnoPage";

/** Legacy URL — main landing is now `/`. */
export default function V2LegacyRedirect() {
  redirect("/");
}
