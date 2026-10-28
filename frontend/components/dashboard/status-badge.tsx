import { Badge } from "@/components/ui/badge";
import type { ElderStatus, LinkRequestStatus } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

const tones = {
  warning: "bg-warning-soft text-warning-text",
  success: "bg-success-soft text-success-text",
  error: "bg-error-soft text-error-text",
  muted: "bg-muted text-muted-foreground",
} as const;

type Tone = keyof typeof tones;

const elderStatus: Record<ElderStatus, { label: string; tone: Tone }> = {
  PENDING_VERIFICATION: { label: "Chờ cuộc gọi đầu tiên", tone: "warning" },
  ACTIVE: { label: "Đang hoạt động", tone: "success" },
  BLOCKED: { label: "Đã chặn", tone: "error" },
};

const requestStatus: Record<LinkRequestStatus, { label: string; tone: Tone }> = {
  pending: { label: "Đang chờ duyệt", tone: "warning" },
  approved: { label: "Đã duyệt", tone: "success" },
  rejected: { label: "Bị từ chối", tone: "muted" },
};

function StatusBadge({ label, tone }: { label: string; tone: Tone }) {
  // Badge defaults to 12px text; body text here never goes below 14px.
  return (
    <Badge className={cn("h-7 rounded-full px-3 text-sm", tones[tone])}>
      {label}
    </Badge>
  );
}

export function ElderStatusBadge({ status }: { status: ElderStatus }) {
  return <StatusBadge {...elderStatus[status]} />;
}

export function LinkRequestStatusBadge({
  status,
}: {
  status: LinkRequestStatus;
}) {
  return <StatusBadge {...requestStatus[status]} />;
}
