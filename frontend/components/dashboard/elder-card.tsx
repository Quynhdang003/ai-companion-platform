import { Phone } from "lucide-react";
import { ElderStatusBadge } from "@/components/dashboard/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import type { Elder } from "@/lib/api/schemas";
import { formatPhone } from "@/lib/format";

export function ElderCard({ elder }: { elder: Elder }) {
  return (
    <Card className="gap-3 text-base">
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-lg font-semibold">{elder.full_name}</h3>
            {elder.preferred_name && (
              <p className="text-muted-foreground">
                Trợ lý gọi là “{elder.preferred_name}”
              </p>
            )}
          </div>
          <ElderStatusBadge status={elder.status} />
        </div>
        <p className="flex items-center gap-2 font-mono">
          <Phone className="h-4 w-4 text-muted-foreground" aria-hidden />
          {formatPhone(elder.phone_e164)}
        </p>
        <p className="text-sm text-muted-foreground">
          {elder.my_role === "owner"
            ? "Bạn là người quản lý"
            : "Bạn được xem thông tin"}
          {elder.status === "PENDING_VERIFICATION" &&
            " · Trợ lý sẽ xin phép khi ông bà gọi lần đầu."}
        </p>
      </CardContent>
    </Card>
  );
}
