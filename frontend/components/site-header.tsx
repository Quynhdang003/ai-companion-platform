import Link from "next/link";
import { UserButton } from "@clerk/nextjs";

export function SiteHeader() {
  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4">
        <Link href="/dashboard" className="text-lg font-semibold">
          AI Companion
        </Link>
        <UserButton />
      </div>
    </header>
  );
}
