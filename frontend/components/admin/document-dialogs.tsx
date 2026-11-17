"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { FilePlus, Pencil } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import {
  KB_CONTENT_MAX,
  KB_SOURCE_MAX,
  KB_TITLE_MAX,
  type KbDocument,
  type KbDocumentInput,
} from "@/lib/api/schemas";
import { useApi } from "@/lib/api/use-api";
import { formatNumber } from "@/lib/format";

const formSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Vui lòng nhập tiêu đề.")
    .max(KB_TITLE_MAX, `Tiêu đề tối đa ${KB_TITLE_MAX} ký tự.`),
  source: z
    .string()
    .trim()
    .max(KB_SOURCE_MAX, `Nguồn tối đa ${KB_SOURCE_MAX} ký tự.`),
  content: z
    .string()
    .trim()
    .min(1, "Vui lòng nhập nội dung.")
    .max(
      KB_CONTENT_MAX,
      `Nội dung tối đa ${formatNumber(KB_CONTENT_MAX)} ký tự.`,
    ),
});

type FormValues = z.infer<typeof formSchema>;

const EMPTY: FormValues = { title: "", source: "", content: "" };

// Backend codes shown above the buttons; the form keeps what was typed.
const SAVE_ERRORS: Record<string, string> = {
  embedding_unavailable:
    "Chưa lưu được vì dịch vụ AI đang bận hoặc đã hết lượt dùng. Nội dung bạn nhập vẫn còn đây, hãy thử lại sau ít phút.",
  llm_not_configured:
    "Máy chủ chưa cấu hình dịch vụ AI (GEMINI_API_KEY) nên chưa lưu được tài liệu.",
  not_found: "Tài liệu này đã bị xóa nên không lưu được nữa.",
};

const largeButton = "h-11 gap-2 px-5 text-base";
const inputClass = "h-11 px-3 text-base md:text-base";
const dialogClass =
  "max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-2xl p-6 sm:max-w-2xl";

function savedToast(saved: KbDocument) {
  toast.success(
    `Đã lưu “${saved.title}” (${saved.chunk_count} đoạn). Trợ lý dùng được ngay.`,
  );
}

export function AddDocumentDialog() {
  const api = useApi();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  return (
    // A click outside doesn't close it: a long text would be lost.
    <Dialog open={open} onOpenChange={setOpen} disablePointerDismissal>
      <DialogTrigger render={<Button className={largeButton} />}>
        <FilePlus className="h-5 w-5" aria-hidden />
        Thêm tài liệu
      </DialogTrigger>
      <DialogContent className={dialogClass} showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">
            Thêm tài liệu
          </DialogTitle>
          <DialogDescription className="text-base">
            Tài liệu được lập chỉ mục ngay khi lưu, cuộc gọi tiếp theo đã dùng
            được.
          </DialogDescription>
        </DialogHeader>
        <DocumentForm
          initial={EMPTY}
          save={(body) => api.createKbDocument(body)}
          onSaved={(saved) => {
            savedToast(saved);
            setOpen(false);
            router.refresh();
          }}
          onCancel={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

type Loaded =
  | { status: "loading" }
  | { status: "ready"; document: KbDocument }
  | { status: "error" };

export function EditDocumentDialog({ id, title }: { id: string; title: string }) {
  const api = useApi();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });

  async function load() {
    setLoaded({ status: "loading" });
    try {
      setLoaded({ status: "ready", document: await api.getKbDocument(id) });
    } catch (error) {
      if (error instanceof ApiError && error.code === "not_found") {
        toast.error("Tài liệu này đã bị xóa.");
        setOpen(false);
        router.refresh();
        return;
      }
      setLoaded({ status: "error" });
    }
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) {
      void load();
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogTrigger
        render={
          <Button
            variant="outline"
            className="h-11 gap-2 px-3 text-base sm:px-4"
            aria-label={`Sửa “${title}”`}
          />
        }
      >
        <Pencil className="h-5 w-5" aria-hidden />
        <span className="hidden sm:inline">Sửa</span>
      </DialogTrigger>
      <DialogContent className={dialogClass} showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold">
            Sửa tài liệu
          </DialogTitle>
          <DialogDescription className="text-base">
            Đổi tiêu đề hoặc nội dung thì tài liệu được lập chỉ mục lại khi
            lưu.
          </DialogDescription>
        </DialogHeader>
        {loaded.status === "loading" && (
          <p className="text-muted-foreground">Đang tải nội dung…</p>
        )}
        {loaded.status === "error" && (
          <div className="flex flex-col items-start gap-3">
            <p role="alert" className="text-error-text">
              Không tải được tài liệu.
            </p>
            <div className="flex gap-2">
              <Button className={largeButton} onClick={() => void load()}>
                Thử lại
              </Button>
              <Button
                variant="outline"
                className={largeButton}
                onClick={() => setOpen(false)}
              >
                Đóng
              </Button>
            </div>
          </div>
        )}
        {loaded.status === "ready" && (
          <DocumentForm
            initial={{
              title: loaded.document.title,
              source: loaded.document.source ?? "",
              content: loaded.document.content,
            }}
            save={(body) => api.updateKbDocument(id, body)}
            onSaved={(saved) => {
              savedToast(saved);
              setOpen(false);
              router.refresh();
            }}
            onCancel={() => setOpen(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function DocumentForm({
  initial,
  save,
  onSaved,
  onCancel,
}: {
  initial: FormValues;
  save: (body: KbDocumentInput) => Promise<KbDocument>;
  onSaved: (saved: KbDocument) => void;
  onCancel: () => void;
}) {
  const {
    control,
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: initial,
  });
  const content = useWatch({ control, name: "content" });

  async function onSubmit(values: FormValues) {
    try {
      onSaved(
        await save({
          title: values.title,
          content: values.content,
          source: values.source || null,
        }),
      );
    } catch (error) {
      const code = error instanceof ApiError ? error.code : null;
      if (code === "title_taken") {
        setError("title", { message: "Đã có tài liệu khác với tiêu đề này." });
        return;
      }
      setError("root", {
        message:
          (code && SAVE_ERRORS[code]) ?? "Không lưu được. Vui lòng thử lại.",
      });
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      <FieldGroup>
        <Field data-invalid={!!errors.title}>
          <FieldLabel htmlFor="kb-title" className="text-base">
            Tiêu đề
          </FieldLabel>
          <Input
            id="kb-title"
            autoComplete="off"
            placeholder="Số tổng đài chính thức"
            aria-invalid={!!errors.title}
            className={inputClass}
            {...register("title")}
          />
          <FieldDescription>
            Trợ lý đọc tiêu đề cùng nội dung, nên hãy đặt tiêu đề rõ ràng.
          </FieldDescription>
          <FieldError errors={[errors.title]} />
        </Field>

        <Field data-invalid={!!errors.content}>
          <FieldLabel htmlFor="kb-content" className="text-base">
            Nội dung
          </FieldLabel>
          <Textarea
            id="kb-content"
            aria-invalid={!!errors.content}
            className="max-h-[45dvh] min-h-48 px-3 text-base md:text-base"
            {...register("content")}
          />
          <FieldDescription className="flex flex-wrap justify-between gap-x-4">
            <span>
              Câu ngắn, rõ ràng; mỗi dòng hoặc đoạn một ý. Trợ lý đọc lại
              nguyên văn đoạn liên quan cho người gọi.
            </span>
            <span className="tabular-nums">
              {formatNumber(content.length)} / {formatNumber(KB_CONTENT_MAX)}{" "}
              ký tự
            </span>
          </FieldDescription>
          <FieldError errors={[errors.content]} />
        </Field>

        <Field data-invalid={!!errors.source}>
          <FieldLabel htmlFor="kb-source" className="text-base">
            Nguồn{" "}
            <span className="font-normal text-muted-foreground">
              (không bắt buộc)
            </span>
          </FieldLabel>
          <Input
            id="kb-source"
            autoComplete="off"
            placeholder="Tên tệp hoặc đường dẫn"
            aria-invalid={!!errors.source}
            className={inputClass}
            {...register("source")}
          />
          <FieldDescription>
            Chỉ để quản trị viên biết tài liệu lấy từ đâu.
          </FieldDescription>
          <FieldError errors={[errors.source]} />
        </Field>

        {errors.root?.message && (
          <p
            role="alert"
            className="rounded-md bg-error-soft px-3 py-2 text-error-text"
          >
            {errors.root.message}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            type="button"
            variant="outline"
            className={largeButton}
            onClick={onCancel}
            disabled={isSubmitting}
          >
            Hủy
          </Button>
          <Button type="submit" className={largeButton} disabled={isSubmitting}>
            {isSubmitting ? "Đang lưu và lập chỉ mục…" : "Lưu tài liệu"}
          </Button>
        </div>
      </FieldGroup>
    </form>
  );
}
