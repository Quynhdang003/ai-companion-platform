import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { RegisterElderForm } from "@/components/dashboard/register-elder-form";

export const metadata: Metadata = { title: "Đăng ký người thân" };

export default function NewElderPage() {
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-2 self-start text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Trang tổng quan
      </Link>
      <div>
        <h1 className="text-2xl font-semibold">Đăng ký người thân</h1>
        <p className="mt-1 text-muted-foreground">
          Người thân của bạn không cần cài ứng dụng hay tạo tài khoản, chỉ cần
          gọi điện.
        </p>
      </div>
      <RegisterElderForm />
    </div>
  );
}
