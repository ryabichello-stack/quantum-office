"use client";

import { Sparkles } from "lucide-react";
import type { KnowledgeSource } from "@/lib/api";

export function DelnoResultCard({
  title = "DELNO",
  subtitle,
  body,
  sources,
  tags,
}: {
  title?: string;
  subtitle?: string;
  body: string;
  sources?: KnowledgeSource[];
  tags?: string[];
}) {
  return (
    <div className="delno-result">
      <div className="result-head">
        <span>
          <Sparkles /> {title}
        </span>
        {subtitle ? <small>{subtitle}</small> : null}
      </div>
      <p style={{ margin: 0 }}>{body}</p>
      {tags && tags.length > 0 && (
        <div className="result-tags">
          {tags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      )}
      {sources && sources.length > 0 && (
        <ul className="msg-sources">
          {sources.map((s, i) => (
            <li key={i}>{s.title || s.citation || s.document_id || "Источник KB"}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
