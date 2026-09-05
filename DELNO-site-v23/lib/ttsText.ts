/** Brand and TTS-friendly text before speech synthesis. */
export function prepareTtsText(text: string): string {
  return text
    .replace(/\bDELNO\b/g, "дельно")
    .replace(/\bDelno\b/g, "дельно")
    .replace(/\bdelno\b/g, "дельно");
}
