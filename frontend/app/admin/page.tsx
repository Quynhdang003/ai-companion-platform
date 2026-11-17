import type { Metadata } from "next";
import { Suspense } from "react";
import { ShieldAlert } from "lucide-react";
import { AddDocumentDialog } from "@/components/admin/document-dialogs";
import { KbEmpty, KbSearch, KbTable } from "@/components/admin/kb-documents";
import { getServerApi } from "@/lib/api/server";
import { KB_QUERY_MAX } from "@/lib/api/schemas";

export const metadata: Metadata = { title: "Tài liệu kiến thức" };

export default function AdminKbPage({ searchParams }: PageProps<"/admin">) {
  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Tài liệu kiến thức</h1>
          <p className="mt-1 max-w-2xl text-muted-foreground">
            Trợ lý tra các tài liệu này để trả lời người gọi. Tài liệu được lập
            chỉ mục ngay khi lưu.
          </p>
        </div>
        <AddDocumentDialog />
      </div>
      <p className="flex items-start gap-3 rounded-xl bg-warning-soft p-4 text-warning-text">
        <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0" aria-hidden />
        Bất kỳ ai gọi tới cũng có thể được nghe nội dung tài liệu, kể cả số
        lạ. Đừng đưa thông tin cá nhân vào tài liệu.
      </p>
      {/* The query and the API both read the request. */}
      <Suspense fallback={<p className="text-muted-foreground">Đang tải…</p>}>
        <KbDocuments searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function KbDocuments({
  searchParams,
}: Pick<PageProps<"/admin">, "searchParams">) {
  const { q: raw } = await searchParams;
  const q = (typeof raw === "string" ? raw : "").trim().slice(0, KB_QUERY_MAX);

  const api = await getServerApi();
  const documents = await api.listKbDocuments(q || undefined);

  return (
    <section className="flex flex-col gap-4" aria-label="Danh sách tài liệu">
      <KbSearch q={q} />
      {q && documents.length > 0 && (
        <p className="text-muted-foreground">
          {documents.length} tài liệu có tiêu đề chứa “{q}”.
        </p>
      )}
      {documents.length > 0 ? (
        <KbTable documents={documents} />
      ) : (
        <KbEmpty q={q} />
      )}
    </section>
  );
}
