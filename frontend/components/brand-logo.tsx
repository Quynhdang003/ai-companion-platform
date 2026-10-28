import Link from "next/link";
import { Sun } from "lucide-react";

export function BrandLogo({ href = "/" }: { href?: string }) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2.5 text-lg font-bold text-foreground"
    >
      <span className="flex size-[38px] items-center justify-center rounded-xl bg-grad-brand text-card">
        <Sun className="size-5" aria-hidden />
      </span>
      Touch the Light
    </Link>
  );
}
