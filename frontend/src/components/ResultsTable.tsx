import { FIELDS } from "../features/fields";
import type { EventRecord } from "../types/api";

export function ResultsTable({ rows }: { rows: EventRecord[] }) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="Matching events">
      <table>
        <thead>
          <tr>
            {FIELDS.map((def) => (
              <th key={def.name} scope="col" title={def.name}>
                {def.label}
              </th>
            ))}
            <th scope="col">File</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.serialno}>
              {FIELDS.map((def) => {
                const value = row[def.name as keyof EventRecord];
                return (
                  <td key={def.name} className={typeof value === "number" ? "num" : undefined}>
                    {value ?? "—"}
                  </td>
                );
              })}
              <td>{row.file}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
