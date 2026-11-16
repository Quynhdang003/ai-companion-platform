"use client";

import { useEffect, useState } from "react";
import { Send } from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/dashboard/status-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/lib/api/use-api";
import type { TelegramLink, TelegramStatus } from "@/lib/api/schemas";
import { formatDate, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

// The backend links the chat within a few seconds of the user pressing Start.
const POLL_MS = 3000;
const largeButton = "h-11 px-5 text-base";

export function TelegramCard({ initial }: { initial: TelegramStatus }) {
  const api = useApi();
  const [status, setStatus] = useState(initial);
  const [link, setLink] = useState<TelegramLink | null>(null);
  const [busy, setBusy] = useState(false);

  // While a connect link is out, wait for the bot to receive it.
  useEffect(() => {
    if (link === null) {
      return;
    }
    const expiresAt = Date.parse(link.expires_at);
    const timer = setInterval(async () => {
      if (Date.now() > expiresAt) {
        setLink(null);
        toast.error(
          "Liên kết đã hết hạn. Bấm “Kết nối Telegram” để lấy liên kết mới.",
        );
        return;
      }
      try {
        const next = await api.getTelegramStatus();
        if (next.connected) {
          setStatus(next);
          setLink(null);
          toast.success("Đã kết nối Telegram.");
        }
      } catch {
        // Keep waiting: the next poll may succeed.
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [api, link]);

  async function connect() {
    setBusy(true);
    try {
      setLink(await api.createTelegramLink());
    } catch {
      toast.error("Không tạo được liên kết. Vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    try {
      setStatus(await api.disconnectTelegram());
      toast.success("Đã ngắt kết nối. Bạn sẽ không nhận cảnh báo qua Telegram nữa.");
    } catch {
      toast.error("Không ngắt kết nối được. Vui lòng thử lại.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="text-base">
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="max-w-2xl">
            <h3 className="text-lg font-semibold">Cảnh báo qua Telegram</h3>
            <p className="text-muted-foreground">
              Khi trợ lý thấy người thân của bạn có nguy cơ cao bị lừa đảo trong
              cuộc gọi, bạn nhận ngay tin nhắn Telegram gồm loại lừa đảo, mức độ
              và thời gian. Tin nhắn không có nội dung cuộc gọi.
            </p>
          </div>
          {status.enabled &&
            (status.connected ? (
              <StatusBadge label="Đã kết nối" tone="success" />
            ) : (
              <StatusBadge label="Chưa kết nối" tone="muted" />
            ))}
        </div>

        {!status.enabled ? (
          <p className="text-sm text-muted-foreground">
            Hệ thống chưa bật gửi cảnh báo qua Telegram.
          </p>
        ) : link !== null ? (
          <div className="flex flex-col gap-3 rounded-lg bg-accent-soft p-4">
            <ol className="list-decimal space-y-1 pl-5">
              <li>Bấm “Mở Telegram” để mở cuộc trò chuyện với bot.</li>
              <li>Trong Telegram, bấm “Bắt đầu” (Start).</li>
            </ol>
            <p className="text-sm text-muted-foreground">
              Liên kết dùng một lần, hết hạn lúc {formatTime(link.expires_at)}.
              Nếu máy tính chưa cài Telegram, hãy mở trang này trên điện thoại.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className={cn(buttonVariants(), largeButton, "gap-2")}
              >
                <Send className="h-5 w-5" aria-hidden />
                Mở Telegram
              </a>
              <Button
                variant="ghost"
                className={largeButton}
                onClick={() => setLink(null)}
              >
                Hủy
              </Button>
              <p className="text-sm text-muted-foreground" aria-live="polite">
                Đang chờ bạn bấm “Bắt đầu”…
              </p>
            </div>
          </div>
        ) : status.connected ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {status.linked_at
                ? `Kết nối từ ${formatDate(status.linked_at)}.`
                : "Đã kết nối."}
            </p>
            <Button
              variant="outline"
              className={largeButton}
              disabled={busy}
              onClick={disconnect}
            >
              Ngắt kết nối
            </Button>
          </div>
        ) : (
          <div>
            <Button className={largeButton} disabled={busy} onClick={connect}>
              Kết nối Telegram
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
