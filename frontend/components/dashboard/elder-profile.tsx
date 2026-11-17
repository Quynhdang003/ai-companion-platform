import { CalendarCheck, Phone, ShieldAlert } from "lucide-react";
import { ElderStatusBadge } from "@/components/dashboard/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ElderDetail } from "@/lib/api/schemas";
import { formatDate, formatPhone, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ElderProfile({ elder }: { elder: ElderDetail }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{elder.full_name}</h1>
          {elder.preferred_name && (
            <p className="mt-1 text-muted-foreground">
              Trợ lý gọi là “{elder.preferred_name}”
            </p>
          )}
        </div>
        <ElderStatusBadge status={elder.status} />
      </div>
      <Card className="gap-3 text-base">
        <CardContent className="flex flex-col gap-3">
          <p className="flex items-center gap-2 font-mono">
            <Phone className="h-4 w-4 text-muted-foreground" aria-hidden />
            {formatPhone(elder.phone_e164)}
          </p>
          <p className="flex items-center gap-2">
            <CalendarCheck
              className="h-4 w-4 text-muted-foreground"
              aria-hidden
            />
            {elder.consent_at
              ? `Đồng ý dùng dịch vụ ngày ${formatDate(elder.consent_at)}`
              : "Chưa đồng ý dùng dịch vụ"}
          </p>
          <p className="text-sm text-muted-foreground">
            {elder.my_role === "owner"
              ? "Bạn là người quản lý"
              : "Bạn được xem thông tin"}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function Stat({
  label,
  value,
  alert = false,
}: {
  label: string;
  value: string;
  alert?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-xl border border-border bg-card p-4",
        alert && "border-error-border bg-error-soft",
      )}
    >
      <p
        className={cn(
          "text-sm text-muted-foreground",
          alert && "flex items-center gap-1.5 text-error-text",
        )}
      >
        {alert && <ShieldAlert className="h-4 w-4" aria-hidden />}
        {label}
      </p>
      <p className={cn("text-2xl font-semibold", alert && "text-error-text")}>
        {value}
      </p>
    </div>
  );
}

export function ActivityStats({
  activity,
}: {
  activity: ElderDetail["activity"];
}) {
  const last = activity.last_call_at;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Cuộc gọi 7 ngày qua" value={String(activity.calls_7d)} />
      <Stat label="Cuộc gọi 30 ngày qua" value={String(activity.calls_30d)} />
      <Stat
        label="Cảnh báo lừa đảo 30 ngày qua"
        value={String(activity.scam_alerts_30d)}
        alert={activity.scam_alerts_30d > 0}
      />
      <Stat
        label="Lần gọi gần nhất"
        value={last ? `${formatTime(last)}, ${formatDate(last)}` : "Chưa có"}
      />
    </div>
  );
}
