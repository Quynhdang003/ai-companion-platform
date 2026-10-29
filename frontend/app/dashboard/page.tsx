import { Suspense } from "react";
import Link from "next/link";
import { UserPlus } from "lucide-react";
import { ElderCard } from "@/components/dashboard/elder-card";
import {
  IncomingRequestCard,
  OutgoingRequestRow,
} from "@/components/dashboard/link-requests";
import { buttonVariants } from "@/components/ui/button";
import { getServerApi } from "@/lib/api/server";
import { cn } from "@/lib/utils";

const primaryLink = cn(buttonVariants(), "h-11 gap-2 px-5 text-base");

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Trang tổng quan</h1>
          <p className="mt-1 text-muted-foreground">
            Người thân bạn đã đăng ký và các yêu cầu liên kết.
          </p>
        </div>
        <Link href="/dashboard/elders/new" className={primaryLink}>
          <UserPlus className="h-5 w-5" aria-hidden />
          Đăng ký người thân
        </Link>
      </div>
      <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
        <DashboardContent />
      </Suspense>
    </div>
  );
}

async function DashboardContent() {
  const api = await getServerApi();
  const me = await api.getMe();
  // Elder routes are family-only; admins manage the knowledge base instead.
  if (me.role === "admin") {
    return (
      <p className="text-muted-foreground">
        Tài khoản quản trị không quản lý người thân.{" "}
        <Link href="/admin" className="text-primary underline">
          Vào trang quản trị
        </Link>
      </p>
    );
  }

  const [elders, incoming, outgoing] = await Promise.all([
    api.listElders(),
    api.listIncomingRequests(),
    api.listOutgoingRequests(),
  ]);

  return (
    <>
      {incoming.length > 0 && (
        <section className="flex flex-col gap-3">
          <h2 className="text-xl font-semibold">Yêu cầu chờ bạn duyệt</h2>
          {incoming.map((request) => (
            <IncomingRequestCard key={request.id} request={request} />
          ))}
        </section>
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Người thân của bạn</h2>
        {elders.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            {elders.map((elder) => (
              <ElderCard key={elder.id} elder={elder} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border bg-card p-6">
            <p>Bạn chưa đăng ký người thân nào.</p>
            <p className="text-muted-foreground">
              Chỉ cần họ tên và số điện thoại người thân hay dùng để gọi.
            </p>
            <Link href="/dashboard/elders/new" className={primaryLink}>
              Đăng ký người thân đầu tiên
            </Link>
          </div>
        )}
      </section>

      {outgoing.length > 0 && (
        <section className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold">Yêu cầu bạn đã gửi</h2>
          <ul className="divide-y divide-border rounded-xl border border-border bg-card px-4">
            {outgoing.map((request) => (
              <OutgoingRequestRow key={request.id} request={request} />
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
