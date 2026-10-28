import { Suspense } from "react";
import type { Metadata } from "next";
import { SignUp } from "@clerk/nextjs";
import { PublicHero } from "@/components/public/public-hero";

export const metadata: Metadata = { title: "Đăng ký" };

export default function SignUpPage() {
  return (
    <PublicHero className="flex flex-1 flex-col">
      <main className="flex flex-1 items-center justify-center px-4 pt-6 pb-16">
        {/* <SignUp> reads the URL path, which is only known at request time. */}
        <Suspense>
          <SignUp />
        </Suspense>
      </main>
    </PublicHero>
  );
}
