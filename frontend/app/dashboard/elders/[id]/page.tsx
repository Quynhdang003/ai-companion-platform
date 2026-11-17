import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { z } from "zod";
import { CallList } from "@/components/dashboard/call-list";
import {
  ActivityStats,
  ElderProfile,
} from "@/components/dashboard/elder-profile";
import { buttonVariants } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { getServerApi } from "@/lib/api/server";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Hoạt động cuộc gọi" };

const pageLink = cn(
  buttonVariants({ variant: "outline" }),
  "h-11 gap-2 px-5 text-base",
);
const cursorSchema = z.iso.datetime({ offset: true });

export default function ElderPage({
  params,
  searchParams,
}: PageProps<"/dashboard/elders/[id]">) {
  return (
    <div className="flex flex-col gap-8">
      <Link
        href="/dashboard"
        className="inline-flex items-center gap-2 self-start text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Trang tổng quan
      </Link>
      {/* Params, the query and the API all read the request. */}
      <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
        <ElderActivity params={params} searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function ElderActivity({
  params,
  searchParams,
}: Pick<PageProps<"/dashboard/elders/[id]">, "params" | "searchParams">) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  // A malformed cursor is ignored: back to the newest calls.
  const cursor = cursorSchema.safeParse(query.before);
  const before = cursor.success ? cursor.data : undefined;

  const api = await getServerApi();
  const [elder, page] = await Promise.all([
    api.getElder(id),
    api.listElderCalls(id, before),
  ]).catch((error: unknown) => {
    // Not linked, no such elder, a malformed id, or an admin: all "not found".
    if (error instanceof ApiError && [403, 404, 422].includes(error.status)) {
      notFound();
    }
    throw error;
  });

  return (
    <>
      <ElderProfile elder={elder} />

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Hoạt động</h2>
        <ActivityStats activity={elder.activity} />
      </section>

      <section className="flex flex-col gap-3">
        <div>
          <h2 className="text-xl font-semibold">Các cuộc gọi</h2>
          <p className="mt-1 text-muted-foreground">
            Chỉ có thời gian, thời lượng và cảnh báo lừa đảo. Nội dung cuộc gọi
            không bao giờ hiện ở đây.
          </p>
        </div>
        {page.calls.length > 0 ? (
          <CallList calls={page.calls} />
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-card p-6">
            {elder.consent_at === null ? (
              <p>
                Người thân chưa đồng ý dùng dịch vụ. Cuộc gọi sẽ hiện ở đây kể
                từ cuộc gọi người thân đồng ý.
              </p>
            ) : before ? (
              <p>Không còn cuộc gọi nào cũ hơn.</p>
            ) : (
              <p>Chưa có cuộc gọi nào.</p>
            )}
          </div>
        )}
        {(before || page.next_before) && (
          <nav className="flex flex-wrap gap-3" aria-label="Trang cuộc gọi">
            {before && (
              <Link href={`/dashboard/elders/${id}`} className={pageLink}>
                Về cuộc gọi mới nhất
              </Link>
            )}
            {page.next_before && (
              <Link
                href={`/dashboard/elders/${id}?before=${encodeURIComponent(page.next_before)}`}
                className={pageLink}
              >
                Cuộc gọi cũ hơn
                <ChevronRight className="h-5 w-5" aria-hidden />
              </Link>
            )}
          </nav>
        )}
      </section>
    </>
  );
}
