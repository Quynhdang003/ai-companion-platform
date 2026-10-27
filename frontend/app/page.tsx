import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 p-4">
      <h1 className="text-2xl font-semibold">AI Companion</h1>
      <div className="flex gap-3">
        <Link
          href="/sign-in"
          className="rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground"
        >
          Đăng nhập
        </Link>
        <Link
          href="/sign-up"
          className="rounded-md border border-border bg-card px-4 py-2 font-medium"
        >
          Đăng ký
        </Link>
      </div>
    </main>
  );
}
