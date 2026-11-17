import { UserButton } from "@clerk/nextjs";
import { BrandLogo } from "@/components/brand-logo";

/** `home`: where the logo leads (the admin pages pass `/admin`). */
export function SiteHeader({ home = "/dashboard" }: { home?: string }) {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4">
        <BrandLogo href={home} />
        <UserButton />
      </div>
    </header>
  );
}
