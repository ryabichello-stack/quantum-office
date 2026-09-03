"use client";

import { Play } from "lucide-react";

function formatDuration(sec: number | null | undefined) {
  if (!sec || sec <= 0) return "0:00";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function VoicePlayback({
  recordingUrl,
  durationSec,
}: {
  recordingUrl?: string | null;
  durationSec?: number | null;
}) {
  if (!recordingUrl && !durationSec) return null;

  return (
    <div className="voice-playback">
      {recordingUrl ? (
        <a className="voice-play" href={recordingUrl} target="_blank" rel="noreferrer" aria-label="Прослушать запись">
          <Play />
        </a>
      ) : (
        <div className="voice-play" aria-hidden>
          <Play />
        </div>
      )}
      <div className="voice-wave" aria-hidden>
        {Array.from({ length: 24 }).map((_, i) => (
          <i key={i} data-tall={i % 5 === 0 ? "1" : i % 3 === 0 ? "2" : undefined} />
        ))}
      </div>
      <span>{formatDuration(durationSec)}</span>
    </div>
  );
}
