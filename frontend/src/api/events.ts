import type { DatasetSummary, SearchResponse, UploadResponse } from "../types/api";
import { getJson, postFile, type UploadProgress } from "./client";

export type Filters = Record<string, string>;

export function searchEvents(
  filters: Filters,
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  return getJson<SearchResponse>("/events/", { ...filters, page, page_size: pageSize }, { signal });
}

export const uploadArchive = (file: File, onProgress: (p: UploadProgress) => void) =>
  postFile<UploadResponse>("/uploads/", file, onProgress);

export const getSummary = () => getJson<DatasetSummary>("/summary/");
