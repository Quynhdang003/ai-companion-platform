import { Suspense } from "react";
import Link from "next/link";
import { Show, UserButton } from "@clerk/nextjs";
import { BrandLogo } from "@/components/brand-logo";
import { PublicNav, type PublicNavHref } from "@/components/public/public-nav";

const darkPill =
  "inline-flex h-11 items-center rounded-full bg-foreground px-5 font-semibold text-card";

export function PublicHeader({ current }: { current?: PublicNavHref }) {
  return (
    <header className="mx-auto flex w-full max-w-[1200px] flex-wrap items-center justify-between gap-4 px-6 py-[18px]">
      <BrandLogo />
      <PublicNav current={current} />
      <div className="flex items-center gap-2">
        {/* <Show> reads the session, which is only known at request time. */}
        <Suspense fallback={<SignedOutActions />}>
          <Show when="signed-out">
            <SignedOutActions />
          </Show>
          <Show when="signed-in">
            <Link href="/dashboard" className={darkPill}>
              Trang quản lý
            </Link>
            <UserButton />
          </Show>
        </Suspense>
      </div>
    </header>
  );
}

function SignedOutActions() {
  return (
    <>
      <Link
        href="/sign-in"
        className="inline-flex h-11 items-center rounded-full px-4 font-medium text-foreground hover:text-primary"
      >
        Đăng nhập
      </Link>
      <Link href="/sign-up" className={darkPill}>
        Đăng ký
      </Link>
    </>
  );
}
