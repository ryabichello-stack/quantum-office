"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Light markdown: paragraphs, **bold**, images, links — ChatGPT-like bubbles. */
export function HermesMessageBody({ text, className }: { text: string; className?: string }) {
  const blocks = splitBlocks(text || "");
  return (
    <div className={cn("hx-md", className)}>
      {blocks.map((block, i) => {
        if (block.type === "image") {
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={i} className="hx-md-img" src={block.src} alt={block.alt || "Hermes"} />
          );
        }
        if (block.type === "video") {
          return (
            <video key={i} className="hx-md-video" src={block.src} controls playsInline preload="metadata" />
          );
        }
        return (
          <p key={i} className="hx-md-p">
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}

type Block =
  | { type: "text"; text: string }
  | { type: "image"; src: string; alt?: string }
  | { type: "video"; src: string };

function splitBlocks(raw: string): Block[] {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const out: Block[] = [];
  let buf: string[] = [];
  const flush = () => {
    const t = buf.join("\n").trim();
    if (t) out.push({ type: "text", text: t });
    buf = [];
  };
  for (const line of lines) {
    const img = line.match(/^!\[([^\]]*)\]\((data:image\/[^)]+|https?:[^)]+)\)\s*$/);
    if (img) {
      flush();
      out.push({ type: "image", alt: img[1], src: img[2] });
      continue;
    }
    const vid = line.match(/^!\[([^\]]*)\]\((data:video\/[^)]+|https?:[^)]+\.(mp4|webm))\)\s*$/i);
    if (vid) {
      flush();
      out.push({ type: "video", src: vid[2] });
      continue;
    }
    buf.push(line);
  }
  flush();
  return out.length ? out : [{ type: "text", text: raw }];
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https?:[^)]+)\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2]) nodes.push(<strong key={key++}>{m[2]}</strong>);
    else if (m[3]) nodes.push(<code key={key++}>{m[3]}</code>);
    else if (m[4] && m[5])
      nodes.push(
        <a key={key++} href={m[5]} target="_blank" rel="noreferrer">
          {m[4]}
        </a>,
      );
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
