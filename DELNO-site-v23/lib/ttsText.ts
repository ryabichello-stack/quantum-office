/** Brand and TTS-friendly text before speech synthesis. */
export function prepareTtsText(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\[[^\]]*\]/g, "")
    .replace(/\*\*/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\bDELNO\b/g, "дельно")
    .replace(/\bDelno\b/g, "дельно")
    .replace(/\bdelno\b/g, "дельно");
}
