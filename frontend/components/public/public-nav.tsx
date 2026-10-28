import Link from "next/link";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Trang chủ" },
  { href: "/demo", label: "Demo" },
] as const;

export type PublicNavHref = (typeof links)[number]["href"];

// The page passes its own entry: usePathname() would make every public route
// dynamic under cacheComponents.
export function PublicNav({ current }: { current?: PublicNavHref }) {
  return (
    <nav
      aria-label="Mục chính"
      className="flex items-center gap-1 rounded-full border border-border bg-card/70 p-1 text-[15px] max-[900px]:order-3 max-[900px]:w-full max-[900px]:justify-center"
    >
      {links.map((link) => {
        const active = link.href === current;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-full px-4 py-2",
              active
                ? "bg-card font-semibold text-primary shadow-pill"
                : "text-foreground hover:text-primary",
            )}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
