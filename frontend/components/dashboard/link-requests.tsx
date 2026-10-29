import { RequestActions } from "@/components/dashboard/request-actions";
import { LinkRequestStatusBadge } from "@/components/dashboard/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import type { IncomingRequest, OutgoingRequest } from "@/lib/api/schemas";
import { formatDate, formatPhone } from "@/lib/format";

export function IncomingRequestCard({ request }: { request: IncomingRequest }) {
  const { display_name, email } = request.requester;
  const name = display_name ?? email ?? "Một tài khoản chưa có tên";

  return (
    <Card className="text-base">
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <p>
            <span className="font-semibold">{name}</span> xin được xem thông tin
            của <span className="font-semibold">{request.elder.full_name}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            {display_name && email ? `${email} · ` : ""}Gửi ngày{" "}
            {formatDate(request.created_at)}
          </p>
        </div>
        <RequestActions requestId={request.id} requesterName={name} />
      </CardContent>
    </Card>
  );
}

export function OutgoingRequestRow({ request }: { request: OutgoingRequest }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div>
        <p className="font-mono">{formatPhone(request.phone_e164)}</p>
        <p className="text-sm text-muted-foreground">
          {request.elder_full_name
            ? `${request.elder_full_name} · `
            : ""}
          Gửi ngày {formatDate(request.created_at)}
        </p>
      </div>
      <LinkRequestStatusBadge status={request.status} />
    </li>
  );
}
