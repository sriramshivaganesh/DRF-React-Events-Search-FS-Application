import { useCallback, useRef, useState } from "react";
import { searchEvents, type Filters } from "../api/events";
import { ApiError } from "../api/client";
import type { SearchResponse } from "../types/api";

export interface SearchState {
  loading: boolean;
  error: string | null;
  fieldErrors: Record<string, string[]>;
  data: SearchResponse | null;
  /** Filters of the last submitted search; page changes reuse these, not the live form values. */
  filters: Filters | null;
  pageSize: number;
}

const INITIAL: SearchState = { loading: false, error: null, fieldErrors: {}, data: null, filters: null, pageSize: 50 };

export function useSearch() {
  const [state, setState] = useState<SearchState>(INITIAL);
  const controller = useRef<AbortController | null>(null);

  const run = useCallback(async (filters: Filters, page: number, pageSize: number) => {
    controller.current?.abort(); // a newer request supersedes an older one
    const abort = new AbortController();
    controller.current = abort;
    setState((s) => ({ ...s, loading: true, error: null, fieldErrors: {}, filters, pageSize }));
    try {
      const data = await searchEvents(filters, page, pageSize, abort.signal);
      if (abort.signal.aborted) return;
      setState((s) => ({ ...s, loading: false, data }));
    } catch (error) {
      if (abort.signal.aborted) return;
      const apiError = error instanceof ApiError ? error : new ApiError("Unexpected error.", 0);
      setState((s) => ({
        ...s,
        loading: false,
        data: null,
        error: apiError.message,
        fieldErrors: apiError.fieldErrors,
      }));
    }
  }, []);

  const search = useCallback((filters: Filters, pageSize?: number) => run(filters, 1, pageSize ?? state.pageSize), [run, state.pageSize]);
  const goToPage = useCallback(
    (page: number) => {
      if (state.filters) void run(state.filters, page, state.pageSize);
    },
    [run, state.filters, state.pageSize],
  );
  const reset = useCallback(() => {
    controller.current?.abort();
    setState((s) => ({ ...INITIAL, pageSize: s.pageSize }));
  }, []);

  return { state, search, goToPage, reset };
}
