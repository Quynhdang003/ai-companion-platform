import { cn } from "@/lib/utils";
import { PublicHeader } from "@/components/public/public-header";
import type { PublicNavHref } from "@/components/public/public-nav";

// The header sits inside the hero gradient, so every public page starts with this.
export function PublicHero({
  current,
  children,
  className,
}: {
  current?: PublicNavHref;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("bg-hero", className)}>
      <PublicHeader current={current} />
      {children}
    </div>
  );
}
