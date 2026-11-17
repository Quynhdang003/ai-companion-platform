import Link from "next/link";
import { ChevronRight, Phone } from "lucide-react";
import { ElderStatusBadge } from "@/components/dashboard/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import type { Elder } from "@/lib/api/schemas";
import { formatPhone } from "@/lib/format";

export function ElderCard({ elder }: { elder: Elder }) {
  return (
    <Link
      href={`/dashboard/elders/${elder.id}`}
      className="group block rounded-xl focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      <Card className="h-full gap-3 text-base transition-shadow group-hover:shadow-card">
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
              " · Trợ lý sẽ xin phép khi người thân gọi lần đầu."}
          </p>
          <p className="flex items-center gap-1 font-medium text-primary">
            Xem hoạt động cuộc gọi
            <ChevronRight
              className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
              aria-hidden
            />
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}
