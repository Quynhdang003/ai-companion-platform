import { Suspense } from "react";
import type { Metadata } from "next";
import { SignIn } from "@clerk/nextjs";
import { PublicHero } from "@/components/public/public-hero";

export const metadata: Metadata = { title: "Đăng nhập" };

export default function SignInPage() {
  return (
    <PublicHero className="flex flex-1 flex-col">
      <main className="flex flex-1 items-center justify-center px-4 pt-6 pb-16">
        {/* <SignIn> reads the URL path, which is only known at request time. */}
        <Suspense>
          <SignIn />
        </Suspense>
      </main>
    </PublicHero>
  );
}
