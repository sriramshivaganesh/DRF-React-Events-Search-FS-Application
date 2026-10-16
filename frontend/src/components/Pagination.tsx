interface Props {
  page: number;
  totalPages: number;
  disabled: boolean;
  onPage: (page: number) => void;
}

export function Pagination({ page, totalPages, disabled, onPage }: Props) {
  return (
    <nav className="pagination" aria-label="Pagination">
      <button onClick={() => onPage(1)} disabled={disabled || page <= 1}>
        First
      </button>
      <button onClick={() => onPage(page - 1)} disabled={disabled || page <= 1}>
        Previous
      </button>
      <span aria-live="polite">
        Page {page.toLocaleString()} of {totalPages.toLocaleString()}
      </span>
      <button onClick={() => onPage(page + 1)} disabled={disabled || page >= totalPages}>
        Next
      </button>
      <button onClick={() => onPage(totalPages)} disabled={disabled || page >= totalPages}>
        Last
      </button>
    </nav>
  );
}
