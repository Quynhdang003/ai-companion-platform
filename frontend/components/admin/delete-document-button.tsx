"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/use-api";

const largeButton = "h-11 px-5 text-base";

export function DeleteDocumentButton({
  id,
  title,
}: {
  id: string;
  title: string;
}) {
  const api = useApi();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await api.deleteKbDocument(id);
      toast.success(`Đã xóa “${title}”.`);
      setOpen(false);
    } catch (error) {
      if (error instanceof ApiError && error.code === "not_found") {
        toast.error("Tài liệu này đã bị xóa trước đó.");
        setOpen(false);
      } else {
        toast.error("Không xóa được. Vui lòng thử lại.");
      }
    } finally {
      setBusy(false);
      router.refresh();
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        render={
          <Button
            variant="destructive"
            className="h-11 gap-2 px-3 text-base sm:px-4"
            aria-label={`Xóa “${title}”`}
          />
        }
      >
        <Trash2 className="h-5 w-5" aria-hidden />
        <span className="hidden sm:inline">Xóa</span>
      </AlertDialogTrigger>
      <AlertDialogContent className="rounded-2xl p-6">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-xl font-semibold">
            Xóa tài liệu này?
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base">
            “{title}” sẽ bị xóa cùng chỉ mục của nó, trợ lý không trả lời từ
            tài liệu này nữa. Không hoàn tác được.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="-mx-6 -mb-6 rounded-b-2xl p-6 pt-4">
          <AlertDialogCancel className={largeButton} disabled={busy}>
            Hủy
          </AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            className={largeButton}
            disabled={busy}
            onClick={() => void remove()}
          >
            {busy ? "Đang xóa…" : "Xóa tài liệu"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
