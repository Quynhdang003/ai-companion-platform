import { UserButton } from "@clerk/nextjs";
import { BrandLogo } from "@/components/brand-logo";

export function SiteHeader() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4">
        <BrandLogo href="/dashboard" />
        <UserButton />
      </div>
    </header>
  );
}
