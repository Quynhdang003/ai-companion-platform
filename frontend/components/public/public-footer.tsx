import Link from "next/link";

export function PublicFooter() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-[1200px] flex-wrap justify-between gap-4 p-6 text-sm text-muted-foreground">
        {/* Fixed year: reading the clock during prerender is blocked by cacheComponents. */}
        <span>© 2026 Touch the Light · Đồ án tốt nghiệp</span>
        <div className="flex gap-5">
          <Link href="/" className="underline hover:text-foreground">
            Trang chủ
          </Link>
          <Link href="/demo" className="underline hover:text-foreground">
            Demo
          </Link>
        </div>
      </div>
    </footer>
  );
}
