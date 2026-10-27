import { redirect } from "next/navigation";
import { SiteHeader } from "@/components/site-header";
import { getServerApi } from "@/lib/api/server";

// The role check needs the backend before anything renders, so navigations
// into /admin block on the server and non-admins get a plain redirect.
export const instant = false;

// Navigation gate only; admin API routes enforce the role on the backend.
export default async function AdminLayout({ children }: LayoutProps<"/admin">) {
  const api = await getServerApi();
  const me = await api.getMe();
  if (me.role !== "admin") {
    redirect("/dashboard");
  }

  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        {children}
      </main>
    </>
  );
}
