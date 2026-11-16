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

const timeFormatter = new Intl.DateTimeFormat("vi-VN", {
  timeStyle: "short",
  timeZone: "Asia/Ho_Chi_Minh",
});

/** ISO timestamp → time of day in Vietnam time, e.g. `14:32`. */
export function formatTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

const numberFormatter = new Intl.NumberFormat("vi-VN");

/** `20000` → `20.000`. */
export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

/** Seconds → `45 giây`, `3 phút 5 giây`, `1 giờ 2 phút`. */
export function formatDuration(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} giây`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    const rest = seconds % 60;
    return rest ? `${minutes} phút ${rest} giây` : `${minutes} phút`;
  }
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return restMinutes ? `${hours} giờ ${restMinutes} phút` : `${hours} giờ`;
}
