"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/use-api";

export function RequestActions({
  requestId,
  requesterName,
}: {
  requestId: string;
  requesterName: string;
}) {
  const api = useApi();
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function decide(approve: boolean) {
    setBusy(true);
    try {
      if (approve) {
        await api.approveRequest(requestId);
        toast.success(`Đã cho phép ${requesterName} xem thông tin người thân.`);
      } else {
        await api.rejectRequest(requestId);
        toast.success("Đã từ chối yêu cầu.");
      }
    } catch (error) {
      toast.error(
        error instanceof ApiError && error.code === "already_decided"
          ? "Yêu cầu này đã được xử lý trước đó."
          : "Không xử lý được yêu cầu. Vui lòng thử lại.",
      );
    } finally {
      setBusy(false);
      router.refresh();
    }
  }

  return (
    <div className="flex gap-2">
      <Button
        className="h-11 px-5 text-base"
        disabled={busy}
        onClick={() => decide(true)}
      >
        Duyệt
      </Button>
      <Button
        variant="outline"
        className="h-11 px-5 text-base"
        disabled={busy}
        onClick={() => decide(false)}
      >
        Từ chối
      </Button>
    </div>
  );
}
