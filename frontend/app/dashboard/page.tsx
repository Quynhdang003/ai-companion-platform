import { Suspense } from "react";
import type { UserRole } from "@/lib/api/schemas";
import { getServerApi } from "@/lib/api/server";

const roleLabels: Record<UserRole, string> = {
  family: "Gia đình",
  admin: "Quản trị viên",
};

export default function DashboardPage() {
  return (
    <>
      <h1 className="text-2xl font-semibold">Trang tổng quan</h1>
      <Suspense
        fallback={<p className="mt-2 text-muted-foreground">Đang tải…</p>}
      >
        <AccountRole />
      </Suspense>
    </>
  );
}

async function AccountRole() {
  const api = await getServerApi();
  const me = await api.getMe();
  return (
    <p className="mt-2 text-muted-foreground">Vai trò: {roleLabels[me.role]}</p>
  );
}
