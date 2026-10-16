import { useRef, useState } from "react";
import { ApiError, type UploadProgress } from "../api/client";
import { uploadArchive } from "../api/events";
import type { IngestionSummary } from "../types/api";

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; progress: UploadProgress; name: string }
  | { kind: "done"; duplicate: boolean; summary: IngestionSummary }
  | { kind: "error"; message: string; summary?: IngestionSummary };

const n = (value: number) => value.toLocaleString();

export function UploadPanel({ onImported }: { onImported: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<UploadState>({ kind: "idle" });

  const upload = async (file: File) => {
    if (!/\.(tgz|tar\.gz)$/i.test(file.name)) {
      setState({ kind: "error", message: "Please choose a .tgz (or .tar.gz) archive." });
      return;
    }
    setState({ kind: "uploading", name: file.name, progress: { phase: "uploading", percent: 0 } });
    try {
      const result = await uploadArchive(file, (progress) => setState({ kind: "uploading", name: file.name, progress }));
      setState({ kind: "done", duplicate: result.duplicate, summary: result.ingestion });
      onImported();
    } catch (error) {
      const apiError = error instanceof ApiError ? error : new ApiError("Upload failed.", 0);
      const fileErrors = apiError.fieldErrors["file"];
      setState({ kind: "error", message: fileErrors?.[0] ?? apiError.message, summary: apiError.body.ingestion });
    } finally {
      if (input.current) input.current.value = ""; // allow re-selecting the same file
    }
  };

  const busy = state.kind === "uploading";
  return (
    <section className="panel" aria-labelledby="upload-title">
      <h2 id="upload-title">Upload archive</h2>
      <p className="hint">Select the event-log <code>.tgz</code> archive. All files inside are imported in one step.</p>
      <div className="actions">
        <input
          ref={input}
          id="archive-input"
          type="file"
          accept=".tgz,.tar.gz,application/gzip,application/x-gzip"
          className="visually-hidden"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void upload(file);
          }}
        />
        <label htmlFor="archive-input" className={`button primary${busy ? " disabled" : ""}`}>
          {busy ? "Uploading…" : "Upload .tgz archive"}
        </label>
      </div>

      <div aria-live="polite" className="status">
        {state.kind === "uploading" && (
          <>
            <p>
              {state.name}:{" "}
              {state.progress.phase === "uploading"
                ? `uploading ${state.progress.percent}%`
                : "uploaded — importing events, this can take a minute…"}
            </p>
            <progress
              value={state.progress.phase === "uploading" ? state.progress.percent : undefined}
              max={100}
              aria-label="Upload progress"
            />
          </>
        )}
        {state.kind === "done" && (
          <div className="notice success">
            <strong>{state.duplicate ? "Already imported — nothing re-imported." : "Import complete."}</strong>
            <SummaryList summary={state.summary} />
          </div>
        )}
        {state.kind === "error" && (
          <div className="notice error" role="alert">
            <strong>{state.message}</strong>
            {state.summary && <SummaryList summary={state.summary} />}
          </div>
        )}
      </div>
    </section>
  );
}

function SummaryList({ summary }: { summary: IngestionSummary }) {
  return (
    <>
      <dl className="summary">
        <div><dt>Files processed</dt><dd>{n(summary.files_processed)}</dd></div>
        <div><dt>Files skipped</dt><dd>{n(summary.files_skipped)}</dd></div>
        <div><dt>Records read</dt><dd>{n(summary.records_read)}</dd></div>
        <div><dt>Imported</dt><dd>{n(summary.records_imported)}</dd></div>
        <div><dt>Duplicates skipped</dt><dd>{n(summary.records_duplicate)}</dd></div>
        <div><dt>Invalid</dt><dd>{n(summary.records_invalid)}</dd></div>
      </dl>
      {summary.errors.length > 0 && (
        <details>
          <summary>{summary.errors.length} message(s)</summary>
          <ul>
            {summary.errors.slice(0, 20).map((message, index) => (
              <li key={index}>{message}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
