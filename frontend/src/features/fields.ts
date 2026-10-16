/** The 15 searchable event fields: API name, label and client-side validation. */
export type FieldKind = "digits" | "text" | "ip" | "int" | "enum";

export interface FieldDef {
  name: string; // exact API/query-string name
  label: string;
  kind: FieldKind;
  placeholder: string;
}

export const FIELDS: FieldDef[] = [
  { name: "serialno", label: "Serial Number", kind: "digits", placeholder: "1" },
  { name: "version", label: "Version", kind: "digits", placeholder: "2" },
  { name: "account-id", label: "Account ID", kind: "digits", placeholder: "348935949" },
  { name: "instance-id", label: "Instance ID", kind: "text", placeholder: "eni-293216456" },
  { name: "srcaddr", label: "Source IP Address", kind: "ip", placeholder: "159.62.125.136" },
  { name: "dstaddr", label: "Destination IP Address", kind: "ip", placeholder: "30.55.177.194" },
  { name: "srcport", label: "Source Port", kind: "int", placeholder: "152" },
  { name: "dstport", label: "Destination Port", kind: "int", placeholder: "23475" },
  { name: "protocol", label: "Protocol", kind: "int", placeholder: "8" },
  { name: "packets", label: "Packets", kind: "int", placeholder: "10" },
  { name: "bytes", label: "Bytes", kind: "int", placeholder: "3929334" },
  { name: "starttime", label: "Start Time (epoch)", kind: "int", placeholder: "1725850449" },
  { name: "endtime", label: "End Time (epoch)", kind: "int", placeholder: "1725855086" },
  { name: "action", label: "Action", kind: "enum", placeholder: "REJECT" },
  { name: "log-status", label: "Log Status", kind: "enum", placeholder: "OK" },
];

const IPV4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
const IPV6 = /^[0-9a-fA-F:.]+$/;

/** Returns an error message, or null when the (trimmed) value is acceptable. Backend re-validates. */
export function validateField(def: FieldDef, raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  switch (def.kind) {
    case "digits":
    case "int":
      return /^\d+$/.test(value) ? null : `${def.label} must contain digits only.`;
    case "ip": {
      const v4 = IPV4.exec(value);
      if (v4) return v4.slice(1).every((part) => Number(part) <= 255) ? null : `${def.label} must be a valid IP address.`;
      return value.includes(":") && IPV6.test(value) ? null : `${def.label} must be a valid IP address.`;
    }
    case "enum":
      return /^[A-Za-z0-9_]{1,16}$/.test(value) ? null : `${def.label} must be a short alphanumeric word.`;
    default:
      return value.length <= 64 ? null : `${def.label} is too long.`;
  }
}

export function validateAll(values: Record<string, string>): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const def of FIELDS) {
    const message = validateField(def, values[def.name] ?? "");
    if (message) errors[def.name] = message;
  }
  return errors;
}

/** Trimmed, non-empty filters only (mirrors the backend rule that blank fields are ignored). */
export function activeFilters(values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const def of FIELDS) {
    const value = (values[def.name] ?? "").trim();
    if (value) out[def.name] = value;
  }
  return out;
}
