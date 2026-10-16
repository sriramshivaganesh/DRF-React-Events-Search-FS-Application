import { useCallback, useEffect, useState } from "react";
import { getSummary } from "./api/events";
import { Pagination } from "./components/Pagination";
import { ResultsTable } from "./components/ResultsTable";
import { SearchForm } from "./components/SearchForm";
import { UploadPanel } from "./components/UploadPanel";
import { useSearch } from "./hooks/useSearch";
import type { DatasetSummary } from "./types/api";

const PAGE_SIZES = [25, 50, 100, 200];

export default function App() {
  const { state, search, goToPage, reset } = useSearch();
  const [summary, setSummary] = useState<DatasetSummary | null>(null);

  const refreshSummary = useCallback(() => {
    getSummary().then(setSummary).catch(() => setSummary(null));
  }, []);
  useEffect(refreshSummary, [refreshSummary]);

  const { data, loading, error } = state;

  return (
    <div className="app">
      <header>
        <h1>Event Search</h1>
        <p>Search imported network event logs by any single field or any combination of the 15 event fields.</p>
        {summary && (
          <p className="dataset" data-testid="dataset-summary">
            {summary.total_events > 0
              ? `${summary.total_events.toLocaleString()} events from ${summary.source_files.toLocaleString()} files loaded.`
              : "No events loaded yet — upload an archive to begin."}
          </p>
        )}
      </header>

      <main>
        <UploadPanel onImported={refreshSummary} />
        <SearchForm loading={loading} serverErrors={state.fieldErrors} onSearch={(f) => void search(f)} onReset={reset} />

        <section className="panel" aria-labelledby="results-title" aria-busy={loading}>
          <div className="results-head">
            <h2 id="results-title">Results</h2>
            {data && (
              <div className="metrics">
                <span>
                  <strong data-testid="match-count">{data.count.toLocaleString()}</strong> matching records
                </span>
                <span className="time" data-testid="search-time">
                  Search time: <strong>{data.search_time_ms.toFixed(2)} ms</strong> ({data.search_time_seconds.toFixed(4)} s)
                </span>
                <label>
                  Rows per page{" "}
                  <select
                    value={state.pageSize}
                    disabled={loading}
                    onChange={(e) => state.filters && void search(state.filters, Number(e.target.value))}
                  >
                    {PAGE_SIZES.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>

          {loading && <p className="muted" role="status">Searching…</p>}
          {error && (
            <p className="notice error" role="alert">
              {error}
            </p>
          )}
          {!loading && !error && !data && <p className="muted">Enter at least one filter and press Search.</p>}
          {!error && data && data.count === 0 && !loading && (
            <p className="muted" role="status">No events match these filters.</p>
          )}
          {!error && data && data.count > 0 && (
            <>
              <ResultsTable rows={data.results} />
              <Pagination page={data.page} totalPages={data.total_pages} disabled={loading} onPage={goToPage} />
            </>
          )}
        </section>
      </main>
    </div>
  );
}
