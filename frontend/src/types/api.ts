/** Wire types for the Django API (field names are the external, hyphenated ones). */
export interface EventRecord {
  serialno: string;
  version: string | null;
  "account-id": string | null;
  "instance-id": string | null;
  srcaddr: string | null;
  dstaddr: string | null;
  srcport: number | null;
  dstport: number | null;
  protocol: number | null;
  packets: number | null;
  bytes: number | null;
  starttime: number | null;
  endtime: number | null;
  action: string | null;
  "log-status": string | null;
  file: string;
}

export interface SearchResponse {
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  search_time_ms: number;
  search_time_seconds: number;
  results: EventRecord[];
}

export interface IngestionSummary {
  id: number;
  original_name: string;
  status: "running" | "completed" | "failed";
  size_bytes: number;
  files_processed: number;
  files_skipped: number;
  records_read: number;
  records_imported: number;
  records_duplicate: number;
  records_invalid: number;
  errors: string[];
}

export interface UploadResponse {
  detail: string;
  duplicate: boolean;
  ingestion: IngestionSummary;
}

export interface DatasetSummary {
  total_events: number;
  source_files: number;
  completed_ingestions: number;
  latest_ingestion: IngestionSummary | null;
  max_upload_bytes: number;
}

export interface ApiErrorBody {
  detail?: string;
  errors?: Record<string, string[]>;
  ingestion?: IngestionSummary;
}
