import { getAccessToken, type MessagingAttachment } from "@/lib/api";
import { apiHttpUrl } from "./messaging-endpoints";

export const ATTACHMENT_MAX_BYTES = 15 * 1024 * 1024; // mirrors backend 15 MB cap
export const ATTACHMENT_MAX_COUNT = 10;

const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const FILE_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "text/plain",
  "text/csv",
  "application/zip",
];
const ALLOWED_TYPES = new Set([...IMAGE_TYPES, ...FILE_TYPES]);
const ALLOWED_EXTS = new Set([
  "png", "jpg", "jpeg", "webp", "gif",
  "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "zip",
]);

/** `accept` attribute for the file input (types + extensions for robustness). */
export const ATTACHMENT_ACCEPT = [
  ...ALLOWED_TYPES,
  ...[...ALLOWED_EXTS].map((e) => `.${e}`),
].join(",");

function extOf(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i + 1).toLowerCase() : "";
}

/** Client-side pre-validation → an exact error before wasting an upload. */
export function validateAttachment(file: File): "ok" | "type" | "size" {
  const typeOk =
    (file.type && ALLOWED_TYPES.has(file.type)) || ALLOWED_EXTS.has(extOf(file.name));
  if (!typeOk) return "type";
  if (file.size > ATTACHMENT_MAX_BYTES) return "size";
  return "ok";
}

export function attachmentKindOf(file: File): "image" | "file" {
  if (file.type && IMAGE_TYPES.includes(file.type)) return "image";
  return ["png", "jpg", "jpeg", "webp", "gif"].includes(extOf(file.name))
    ? "image"
    : "file";
}

/** Upload failure reason surfaced to the composer (mapped to localized copy). */
export type AttachmentUploadReason = "type" | "size" | "network" | "aborted" | "generic";

export class AttachmentUploadError extends Error {
  readonly reason: AttachmentUploadReason;
  constructor(reason: AttachmentUploadReason) {
    super(reason);
    this.name = "AttachmentUploadError";
    this.reason = reason;
  }
}

function classifyStatus(status: number, body: string): AttachmentUploadReason {
  const text = body.toLowerCase();
  if (text.includes("too_large") || status === 413) return "size";
  if (text.includes("not_allowed") || text.includes("file_type")) return "type";
  return "generic";
}

/**
 * Upload one attachment via multipart XHR so we can report real per-file byte
 * progress (fetch can't stream upload progress). Auth is the in-memory Bearer
 * token (the httpOnly cookie can't cover XHR to the gated endpoint the same way);
 * `credentials: include` still travels the cookie for the refresh path. Resolves
 * with the created attachment, rejects with an {@link AttachmentUploadError}.
 */
export function uploadMessagingAttachment(
  threadId: string,
  file: File,
  opts?: { onProgress?: (percent: number) => void; signal?: AbortSignal },
): Promise<MessagingAttachment> {
  return new Promise((resolve, reject) => {
    const url = apiHttpUrl(`/messaging/threads/${threadId}/attachments`);
    const token = getAccessToken();
    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.withCredentials = true;
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && opts?.onProgress) {
        opts.onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const json = JSON.parse(xhr.responseText) as { data: MessagingAttachment };
          resolve(json.data);
        } catch {
          reject(new AttachmentUploadError("generic"));
        }
      } else {
        reject(new AttachmentUploadError(classifyStatus(xhr.status, xhr.responseText)));
      }
    };
    xhr.onerror = () => reject(new AttachmentUploadError("network"));
    xhr.onabort = () => reject(new AttachmentUploadError("aborted"));

    if (opts?.signal) {
      if (opts.signal.aborted) {
        xhr.abort();
        return;
      }
      opts.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }
    xhr.send(form);
  });
}

/** Human-readable size, e.g. "1.4 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  const mb = kb / 1024;
  return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
}
