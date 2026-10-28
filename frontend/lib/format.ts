/** `+84912345678` → `0912 345 678`; landlines `+842438261234` → `024 3826 1234`. */
export function formatPhone(e164: string): string {
  if (!e164.startsWith("+84")) {
    return e164;
  }
  const national = `0${e164.slice(3)}`;
  return national.length === 11
    ? `${national.slice(0, 3)} ${national.slice(3, 7)} ${national.slice(7)}`
    : `${national.slice(0, 4)} ${national.slice(4, 7)} ${national.slice(7)}`;
}

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  dateStyle: "medium",
  timeZone: "Asia/Ho_Chi_Minh",
});

/** ISO timestamp → Vietnamese date in Vietnam time, e.g. `28 thg 10, 2026`. */
export function formatDate(iso: string): string {
  return dateFormatter.format(new Date(iso));
}
