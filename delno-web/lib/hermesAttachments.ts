import type { OperatorChatAttachment } from "@/lib/api";

export type PendingHermesAttachment = {
  id: string;
  file: File;
  filename: string;
  content_type: string;
  previewUrl?: string;
  kind: "image" | "video" | "file";
};

const MAX_ATTACHMENTS = 4;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_VIDEO_BYTES = 16 * 1024 * 1024;

const IMAGE_RE = /^image\/(jpeg|jpg|png|webp|gif)$/i;
const VIDEO_RE = /^video\/(mp4|webm|quicktime)$/i;

export function validateHermesFile(file: File): string | null {
  if (!file || file.size <= 0) return "Пустой файл";
  if (IMAGE_RE.test(file.type) || /\.(jpe?g|png|webp|gif)$/i.test(file.name)) {
    if (file.size > MAX_IMAGE_BYTES) return "Фото больше 4 МБ";
    return null;
  }
  if (VIDEO_RE.test(file.type) || /\.(mp4|webm|mov)$/i.test(file.name)) {
    if (file.size > MAX_VIDEO_BYTES) return "Видео больше 16 МБ";
    return null;
  }
  if (file.size > MAX_FILE_BYTES) return "Файл больше 8 МБ";
  if (!/\.(pdf|docx|xlsx|csv|txt|md|html?|json)$/i.test(file.name) && !file.type.startsWith("text/")) {
    return "Тип не поддерживается (фото, видео, PDF, DOCX, TXT…)";
  }
  return null;
}

export function makePendingAttachment(file: File): PendingHermesAttachment | { error: string } {
  const err = validateHermesFile(file);
  if (err) return { error: err };
  const isImage = IMAGE_RE.test(file.type) || /\.(jpe?g|png|webp|gif)$/i.test(file.name);
  const isVideo = VIDEO_RE.test(file.type) || /\.(mp4|webm|mov)$/i.test(file.name);
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    file,
    filename: file.name || (isImage ? "photo.jpg" : isVideo ? "clip.mp4" : "file.bin"),
    content_type:
      file.type ||
      (isImage ? "image/jpeg" : isVideo ? "video/mp4" : "application/octet-stream"),
    previewUrl: isImage || isVideo ? URL.createObjectURL(file) : undefined,
    kind: isImage ? "image" : isVideo ? "video" : "file",
  };
}

export function canAddMore(current: number, adding = 1): boolean {
  return current + adding <= MAX_ATTACHMENTS;
}

export async function fileToOperatorAttachment(file: File): Promise<OperatorChatAttachment> {
  const buf = await file.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return {
    filename: file.name || "file",
    content_type: file.type || "application/octet-stream",
    data_base64: btoa(binary),
  };
}

export async function blobToJpegFile(blob: Blob, name = "camera.jpg"): Promise<File> {
  return new File([blob], name, { type: blob.type || "image/jpeg" });
}
