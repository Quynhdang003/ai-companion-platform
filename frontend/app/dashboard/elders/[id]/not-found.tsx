import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function ElderNotFound() {
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border bg-card p-6">
      <h1 className="text-xl font-semibold">Không tìm thấy người thân này</h1>
      <p className="text-muted-foreground">
        Có thể bạn chưa được liên kết với người thân này, hoặc đường dẫn không
        đúng.
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
