import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { FIELDS } from "./features/fields";
import type { EventRecord, SearchResponse } from "./types/api";

const record = (serialno: string, file = "events_2025.log"): EventRecord => ({
  serialno, version: "2", "account-id": "348935949", "instance-id": "eni-293216456",
  srcaddr: "159.62.125.136", dstaddr: "30.55.177.194", srcport: 152, dstport: 23475, protocol: 8,
  packets: 10, bytes: 3929334, starttime: 1725850449, endtime: 1725855086, action: "REJECT", "log-status": "OK", file,
});

const searchBody = (overrides: Partial<SearchResponse> = {}): SearchResponse => ({
  count: 1, page: 1, page_size: 50, total_pages: 1, search_time_ms: 12.456, search_time_seconds: 0.012456,
  results: [record("1")], ...overrides,
});

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

const summaryBody = { total_events: 100, source_files: 4, completed_ingestions: 1, latest_ingestion: null, max_upload_bytes: 1 };

let fetchMock: ReturnType<typeof vi.fn>;
const searchCalls = () => fetchMock.mock.calls.map(([url]) => new URL(String(url), "http://x")).filter((u) => u.pathname.endsWith("/events/"));

function mockApi(handler: (url: URL) => Promise<Response>) {
  fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://x");
    return url.pathname.endsWith("/summary/") ? json(summaryBody) : handler(url);
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => mockApi(() => json(searchBody())));
afterEach(() => vi.unstubAllGlobals());

describe("search form", () => {
  it("renders an input for every one of the 15 fields", () => {
    render(<App />);
    expect(FIELDS).toHaveLength(15);
    for (const def of FIELDS) expect(screen.getByLabelText(def.label)).toBeInTheDocument();
    expect(screen.getByLabelText("Source IP Address")).toHaveAttribute("name", "srcaddr");
    expect(screen.getByLabelText("Account ID")).toHaveAttribute("name", "account-id");
  });

  it("refuses an empty search with a message and no request", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/at least one field/i)).toBeInTheDocument();
    expect(searchCalls()).toHaveLength(0);
  });

  it("validates numeric fields on the client", async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText("Source Port"), "12a");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/Source Port must contain digits only/)).toBeInTheDocument();
    expect(searchCalls()).toHaveLength(0);
  });

  it("submits a single-field search, ignoring blank fields", async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "reject");
    await userEvent.type(screen.getByLabelText("Source Port"), "   ");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByTestId("match-count");
    const [url] = searchCalls();
    expect(Object.fromEntries(url.searchParams)).toEqual({ action: "reject", page: "1", page_size: "50" });
  });

  it("submits a multi-field search with the exact API names", async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText("Account ID"), "348935949");
    await userEvent.type(screen.getByLabelText("Protocol"), "8");
    await userEvent.type(screen.getByLabelText("Log Status"), "OK");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByTestId("match-count");
    const params = Object.fromEntries(searchCalls()[0].searchParams);
    expect(params).toMatchObject({ "account-id": "348935949", protocol: "8", "log-status": "OK" });
  });

  it("clear resets inputs and results", async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "REJECT");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByTestId("match-count");
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByLabelText("Action")).toHaveValue("");
    expect(screen.queryByTestId("match-count")).not.toBeInTheDocument();
  });

  it("disables the search button while a request is in flight", async () => {
    let release!: () => void;
    mockApi(() => new Promise((resolve) => (release = () => resolve(new Response(JSON.stringify(searchBody()))))));
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "REJECT");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.getByRole("button", { name: "Searching…" })).toBeDisabled();
    release();
    await screen.findByTestId("match-count");
    expect(screen.getByRole("button", { name: "Search" })).toBeEnabled();
  });
});

describe("results", () => {
  it("shows every field, the source file, count and search time", async () => {
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "REJECT");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    const table = await screen.findByRole("table");
    const row = within(table).getAllByRole("row")[1];
    for (const text of ["1", "2", "348935949", "eni-293216456", "159.62.125.136", "30.55.177.194", "152", "23475", "8", "10", "3929334", "1725850449", "1725855086", "REJECT", "OK", "events_2025.log"]) {
      expect(within(row).getAllByText(text).length).toBeGreaterThan(0);
    }
    expect(within(table).getAllByRole("columnheader")).toHaveLength(16);
    expect(screen.getByTestId("match-count")).toHaveTextContent("1");
    expect(screen.getByTestId("search-time")).toHaveTextContent("12.46 ms");
    expect(screen.getByTestId("search-time")).toHaveTextContent("0.0125 s");
  });

  it("paginates while preserving the submitted filters, not later edits", async () => {
    mockApi((url) => json(searchBody({ count: 120, total_pages: 3, page: Number(url.searchParams.get("page")) })));
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "REJECT");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Page 1 of 3");
    await userEvent.type(screen.getByLabelText("Version"), "9"); // edited but never submitted
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Page 2 of 3");
    const last = searchCalls().slice(-1)[0];
    expect(Object.fromEntries(last.searchParams)).toEqual({ action: "REJECT", page: "2", page_size: "50" });
    await userEvent.click(screen.getByRole("button", { name: "Last" }));
    await screen.findByText("Page 3 of 3");
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("shows an empty state for zero matches", async () => {
    mockApi(() => json(searchBody({ count: 0, total_pages: 0, results: [] })));
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "REJECT");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No events match these filters.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows API errors and field errors from the server", async () => {
    mockApi(() => json({ detail: "Validation failed.", errors: { srcaddr: ["srcaddr must be a valid IPv4/IPv6 address"] } }, 400));
    render(<App />);
    await userEvent.type(screen.getByLabelText("Source IP Address"), "1.2.3.4");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Validation failed.")).toBeInTheDocument();
    expect(screen.getByText(/srcaddr must be a valid IPv4\/IPv6 address/)).toBeInTheDocument();
  });

  it("shows a friendly message when the server is unreachable", async () => {
    mockApi(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<App />);
    await userEvent.type(screen.getByLabelText("Action"), "REJECT");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/Cannot reach the server/)).toBeInTheDocument();
  });

  it("shows the dataset summary", async () => {
    render(<App />);
    expect(await screen.findByTestId("dataset-summary")).toHaveTextContent("100 events from 4 files loaded.");
  });
});

describe("upload", () => {
  class FakeXhr {
    static response: { status: number; body: unknown } = { status: 201, body: {} };
    upload: { onprogress?: (e: unknown) => void; onload?: () => void } = {};
    status = 0;
    responseText = "";
    timeout = 0;
    onload?: () => void;
    onerror?: () => void;
    ontimeout?: () => void;
    open = vi.fn();
    send = vi.fn(() => {
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      this.upload.onload?.();
      this.status = FakeXhr.response.status;
      this.responseText = JSON.stringify(FakeXhr.response.body);
      setTimeout(() => this.onload?.());
    });
  }
  const ingestion = {
    id: 1, original_name: "events.tgz", status: "completed", size_bytes: 10, files_processed: 7, files_skipped: 0,
    records_read: 7841, records_imported: 4321, records_duplicate: 3520, records_invalid: 0, errors: [],
  };

  beforeEach(() => vi.stubGlobal("XMLHttpRequest", FakeXhr));

  const choose = (name: string) =>
    userEvent.upload(document.getElementById("archive-input") as HTMLInputElement, new File(["x"], name), { applyAccept: false });

  it("uploads an archive and shows the ingestion summary", async () => {
    FakeXhr.response = { status: 201, body: { detail: "Archive imported.", duplicate: false, ingestion } };
    render(<App />);
    await choose("events.tgz");
    expect(await screen.findByText("Import complete.")).toBeInTheDocument();
    expect(screen.getByText("4,321")).toBeInTheDocument();
    expect(screen.getByText("3,520")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/summary/"))).toHaveLength(2));
  });

  it("reports an already-imported archive", async () => {
    FakeXhr.response = { status: 200, body: { detail: "dup", duplicate: true, ingestion } };
    render(<App />);
    await choose("events.tgz");
    expect(await screen.findByText(/Already imported/)).toBeInTheDocument();
  });

  it("shows server-side upload failures", async () => {
    FakeXhr.response = { status: 400, body: { detail: "Validation failed.", errors: { file: ["The file is not a gzip-compressed tar archive."] } } };
    render(<App />);
    await choose("events.tgz");
    expect(await screen.findByRole("alert")).toHaveTextContent("not a gzip-compressed tar archive");
  });

  it("rejects non-tgz files before uploading", async () => {
    render(<App />);
    await choose("notes.txt");
    expect(await screen.findByRole("alert")).toHaveTextContent("Please choose a .tgz");
  });
});
