import type { ApiErrorBody } from "../types/api";

/** Same-origin by default (nginx / Vite proxy /api to Django); override at build time if needed. */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api/v1";

const DEFAULT_TIMEOUT_MS = 30_000;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fieldErrors: Record<string, string[]> = {},
    readonly body: ApiErrorBody = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function toApiError(status: number, body: unknown): ApiError {
  const parsed = (typeof body === "object" && body !== null ? body : {}) as ApiErrorBody;
  const message = parsed.detail ?? `Request failed with status ${status}.`;
  return new ApiError(message, status, parsed.errors ?? {}, parsed);
}

/** GET JSON with timeout + cancellation; throws ApiError for HTTP and network problems. */
export async function getJson<T>(
  path: string,
  params?: Record<string, string | number>,
  options: { signal?: AbortSignal; timeoutMs?: number } = {},
): Promise<T> {
  const query = params ? "?" + new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString() : "";
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  options.signal?.addEventListener("abort", () => timeout.abort());
  try {
    const response = await fetch(`${API_BASE_URL}${path}${query}`, { signal: timeout.signal });
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new ApiError("The server returned an unreadable response.", response.status);
    }
    if (!response.ok) throw toApiError(response.status, body);
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (options.signal?.aborted) throw error; // caller cancelled: let it handle quietly
    if (timeout.signal.aborted) throw new ApiError("The request timed out. Please try again.", 0);
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
  } finally {
    clearTimeout(timer);
  }
}

export interface UploadProgress {
  /** 0-100 while bytes are being sent; "processing" once the server is importing. */
  phase: "uploading" | "processing";
  percent: number;
}

/** POST multipart with upload progress (fetch cannot report upload progress, XHR can). */
export function postFile<T>(
  path: string,
  file: File,
  onProgress: (progress: UploadProgress) => void,
  timeoutMs = 15 * 60_000,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}${path}`);
    xhr.timeout = timeoutMs;
    xhr.responseType = "text";
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress({ phase: "uploading", percent: Math.round((event.loaded / event.total) * 100) });
    };
    xhr.upload.onload = () => onProgress({ phase: "processing", percent: 100 });
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* handled below */
      }
      if (xhr.status >= 200 && xhr.status < 300 && body !== null) resolve(body as T);
      else if (body === null) reject(new ApiError("The server returned an unreadable response.", xhr.status));
      else reject(toApiError(xhr.status, body));
    };
    xhr.onerror = () => reject(new ApiError("Upload failed: cannot reach the server.", 0));
    xhr.ontimeout = () => reject(new ApiError("Upload timed out.", 0));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
