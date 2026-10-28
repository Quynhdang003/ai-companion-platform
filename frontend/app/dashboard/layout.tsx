import { SiteHeader } from "@/components/site-header";

export default function DashboardLayout({
  children,
}: LayoutProps<"/dashboard">) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {children}
      </main>
    </>
  );
}
