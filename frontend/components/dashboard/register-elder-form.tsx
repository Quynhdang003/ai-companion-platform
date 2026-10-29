"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { MailCheck } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { useApi } from "@/lib/api/use-api";
import { cn } from "@/lib/utils";

// Loose client check for quick feedback; the backend decides what is a valid VN number.
const formSchema = z.object({
  full_name: z
    .string()
    .trim()
    .min(1, "Vui lòng nhập họ và tên.")
    .max(100, "Họ và tên tối đa 100 ký tự."),
  phone: z
    .string()
    .trim()
    .min(1, "Vui lòng nhập số điện thoại.")
    .regex(/^\+?[\d\s.-]{8,20}$/, "Số điện thoại chỉ gồm chữ số."),
  preferred_name: z.string().trim().max(50, "Cách xưng hô tối đa 50 ký tự."),
});

type FormValues = z.infer<typeof formSchema>;

const inputClass = "h-11 px-3 text-base md:text-base";

export function RegisterElderForm() {
  const api = useApi();
  const router = useRouter();
  const [linkRequested, setLinkRequested] = useState(false);
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { full_name: "", phone: "", preferred_name: "" },
  });

  async function onSubmit(values: FormValues) {
    try {
      const registration = await api.createElder({
        full_name: values.full_name,
        phone: values.phone,
        preferred_name: values.preferred_name || null,
      });
      if (registration.result === "created") {
        toast.success(`Đã đăng ký ${registration.elder.full_name}.`);
        router.push("/dashboard");
      } else {
        setLinkRequested(true);
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === "invalid_phone") {
        setError("phone", {
          message:
            "Số điện thoại không hợp lệ. Hãy nhập số di động hoặc số bàn ở Việt Nam.",
        });
      } else if (error instanceof ApiError && error.code === "already_linked") {
        setError("phone", {
          message: "Bạn đã được liên kết với người thân dùng số này.",
        });
      } else {
        toast.error("Không đăng ký được. Vui lòng thử lại.");
      }
    }
  }

  if (linkRequested) {
    return (
      <div className="flex flex-col items-start gap-4 rounded-xl border border-border bg-card p-6">
        <span className="flex size-12 items-center justify-center rounded-xl bg-accent-soft text-primary">
          <MailCheck className="h-6 w-6" aria-hidden />
        </span>
        <h2 className="text-xl font-semibold">Đã gửi yêu cầu liên kết</h2>
        <p className="text-muted-foreground">
          Số điện thoại này đã được một người nhà khác đăng ký. Chúng tôi đã gửi
          yêu cầu để người quản lý duyệt. Khi được duyệt, người thân sẽ hiện
          trong trang tổng quan của bạn.
        </p>
        <Link
          href="/dashboard"
          className={cn(buttonVariants(), "h-11 px-5 text-base")}
        >
          Về trang tổng quan
        </Link>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="rounded-xl border border-border bg-card p-6"
    >
      <FieldGroup>
        <Field data-invalid={!!errors.full_name}>
          <FieldLabel htmlFor="full_name" className="text-base">
            Họ và tên
          </FieldLabel>
          <Input
            id="full_name"
            autoComplete="off"
            aria-invalid={!!errors.full_name}
            className={inputClass}
            {...register("full_name")}
          />
          <FieldError errors={[errors.full_name]} />
        </Field>

        <Field data-invalid={!!errors.phone}>
          <FieldLabel htmlFor="phone" className="text-base">
            Số điện thoại
          </FieldLabel>
          <Input
            id="phone"
            type="tel"
            inputMode="tel"
            autoComplete="off"
            placeholder="0912 345 678"
            aria-invalid={!!errors.phone}
            className={inputClass}
            {...register("phone")}
          />
          <FieldDescription>
            Số người thân hay dùng để gọi (di động hoặc số bàn). Trợ lý nhận ra
            người thân qua số này.
          </FieldDescription>
          <FieldError errors={[errors.phone]} />
        </Field>

        <Field data-invalid={!!errors.preferred_name}>
          <FieldLabel htmlFor="preferred_name" className="text-base">
            Cách xưng hô{" "}
            <span className="font-normal text-muted-foreground">
              (không bắt buộc)
            </span>
          </FieldLabel>
          <Input
            id="preferred_name"
            autoComplete="off"
            placeholder="bà Lan"
            aria-invalid={!!errors.preferred_name}
            className={inputClass}
            {...register("preferred_name")}
          />
          <FieldDescription>
            Trợ lý sẽ chào người thân bằng tên này.
          </FieldDescription>
          <FieldError errors={[errors.preferred_name]} />
        </Field>

        <p className="text-sm text-muted-foreground">
          Lần đầu người thân gọi, trợ lý sẽ xin phép trước khi bắt đầu trò
          chuyện.
        </p>

        <Button
          type="submit"
          disabled={isSubmitting}
          className="h-11 self-start px-6 text-base"
        >
          {isSubmitting ? "Đang đăng ký…" : "Đăng ký"}
        </Button>
      </FieldGroup>
    </form>
  );
}
