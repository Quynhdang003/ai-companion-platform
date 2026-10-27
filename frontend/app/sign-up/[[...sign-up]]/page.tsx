import { Suspense } from "react";
import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-4">
      {/* <SignUp> reads the URL path, which is only known at request time. */}
      <Suspense>
        <SignUp />
      </Suspense>
    </main>
  );
}
