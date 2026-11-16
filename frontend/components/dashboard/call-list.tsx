import { Clock, PhoneIncoming, ShieldAlert } from "lucide-react";
import { toneClasses, type Tone } from "@/components/dashboard/status-badge";
import type { Call, RiskLevel } from "@/lib/api/schemas";
import { formatDate, formatDuration, formatTime } from "@/lib/format";
import { riskLevelLabels, scamTypeLabels } from "@/lib/labels";
import { cn } from "@/lib/utils";

const riskTones: Record<RiskLevel, Tone> = {
  high: "error",
  medium: "warning",
  low: "muted",
  none: "muted",
};

function ScamAlertTag({ alert }: { alert: Call["scam_alerts"][number] }) {
  // Wraps instead of a fixed-height badge: type names are long on a phone.
  return (
    <li
      className={cn(
        "inline-flex items-start gap-2 rounded-xl px-3 py-1.5 text-sm",
        toneClasses[riskTones[alert.risk_level]],
      )}
    >
      <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>
        <span className="font-medium">{riskLevelLabels[alert.risk_level]}</span>
        {" · "}
        {scamTypeLabels[alert.scam_type]}
        {" · "}
        {formatTime(alert.created_at)}
      </span>
    </li>
  );
}

export function CallList({ calls }: { calls: Call[] }) {
  return (
    <ul className="divide-y divide-border rounded-xl border border-border bg-card px-4">
      {calls.map((call) => (
        <li
          key={call.id}
          className="flex flex-col gap-3 py-4 md:flex-row md:items-start md:justify-between"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-primary">
              <PhoneIncoming className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <p className="font-medium">
                {formatDate(call.started_at)} · {formatTime(call.started_at)}
              </p>
              <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" aria-hidden />
                {call.duration_seconds === null
                  ? "Chưa có thời lượng"
                  : formatDuration(call.duration_seconds)}
              </p>
            </div>
          </div>
          {call.scam_alerts.length > 0 && (
            <ul
              className="flex flex-col gap-2 md:max-w-md md:items-end"
              aria-label="Cảnh báo lừa đảo trong cuộc gọi"
            >
              {call.scam_alerts.map((alert) => (
                <ScamAlertTag
                  key={`${alert.scam_type}-${alert.created_at}`}
                  alert={alert}
                />
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
