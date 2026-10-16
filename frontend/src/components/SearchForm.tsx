import { useState, type FormEvent } from "react";
import type { Filters } from "../api/events";
import { FIELDS, activeFilters, validateAll } from "../features/fields";

interface Props {
  loading: boolean;
  serverErrors: Record<string, string[]>;
  onSearch: (filters: Filters) => void;
  onReset: () => void;
}

export function SearchForm({ loading, serverErrors, onSearch, onReset }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [clientErrors, setClientErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (loading) return; // block double submits while a request is in flight
    const errors = validateAll(values);
    const filters = activeFilters(values);
    setClientErrors(errors);
    if (Object.keys(errors).length > 0) {
      setFormError(null);
      return;
    }
    if (Object.keys(filters).length === 0) {
      setFormError("Enter a value in at least one field to search.");
      return;
    }
    setFormError(null);
    onSearch(filters);
  };

  const reset = () => {
    setValues({});
    setClientErrors({});
    setFormError(null);
    onReset();
  };

  return (
    <form className="panel" onSubmit={submit} noValidate aria-label="Search events">
      <h2>Search</h2>
      <p className="hint">Fill in any fields; all filled fields must match (AND). Blank fields are ignored.</p>
      <div className="field-grid">
        {FIELDS.map((def) => {
          const message = clientErrors[def.name] ?? serverErrors[def.name]?.[0];
          const id = `field-${def.name}`;
          return (
            <div className="field" key={def.name}>
              <label htmlFor={id}>{def.label}</label>
              <input
                id={id}
                name={def.name}
                value={values[def.name] ?? ""}
                placeholder={def.placeholder}
                inputMode={def.kind === "int" || def.kind === "digits" ? "numeric" : "text"}
                autoComplete="off"
                spellCheck={false}
                aria-invalid={message ? true : undefined}
                aria-describedby={message ? `${id}-error` : undefined}
                onChange={(e) => setValues((v) => ({ ...v, [def.name]: e.target.value }))}
              />
              <code className="api-name">{def.name}</code>
              {message && (
                <span className="field-error" id={`${id}-error`} role="alert">
                  {message}
                </span>
              )}
            </div>
          );
        })}
      </div>
      {formError && (
        <p className="form-error" role="alert">
          {formError}
        </p>
      )}
      <div className="actions">
        <button type="submit" className="primary" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </button>
        <button type="button" onClick={reset}>
          Clear
        </button>
      </div>
    </form>
  );
}
