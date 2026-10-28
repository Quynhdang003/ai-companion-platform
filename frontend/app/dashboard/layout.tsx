import { SiteHeader } from "@/components/site-header";
import { Toaster } from "@/components/ui/sonner";

export default function DashboardLayout({
  children,
}: LayoutProps<"/dashboard">) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {children}
      </main>
      {/* Fixed theme: the shadcn wrapper reads next-themes, which this light-only app doesn't mount. */}
      <Toaster theme="light" position="top-center" />
    </>
  );
}
