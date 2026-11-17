import Form from "next/form";
import Link from "next/link";
import { Search } from "lucide-react";
import { DeleteDocumentButton } from "@/components/admin/delete-document-button";
import { EditDocumentDialog } from "@/components/admin/document-dialogs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { KB_QUERY_MAX, type KbDocumentSummary } from "@/lib/api/schemas";
import { formatDate, formatTime } from "@/lib/format";

/** Title search: a GET form, so the query lives in the URL (`/admin?q=`). */
export function KbSearch({ q }: { q: string }) {
  return (
    <Form action="/admin" role="search" className="flex max-w-xl gap-2">
      <Input
        // Remount when the URL changes, so the box shows the current query.
        key={q}
        name="q"
        type="search"
        defaultValue={q}
        maxLength={KB_QUERY_MAX}
        placeholder="Tìm theo tiêu đề"
        aria-label="Tìm tài liệu theo tiêu đề"
        className="h-11 px-3 text-base md:text-base"
      />
      <Button
        type="submit"
        variant="outline"
        className="h-11 gap-2 px-5 text-base"
      >
        <Search className="h-5 w-5" aria-hidden />
        Tìm
      </Button>
    </Form>
  );
}

export function KbEmpty({ q }: { q: string }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-xl border border-dashed border-border bg-card p-6">
      {q ? (
        <>
          <p>Không có tài liệu nào có tiêu đề chứa “{q}”.</p>
          <Link href="/admin" className="text-primary underline">
            Xem tất cả tài liệu
          </Link>
        </>
      ) : (
        <>
          <p>Chưa có tài liệu nào.</p>
          <p className="text-muted-foreground">
            Bấm “Thêm tài liệu” để trợ lý có thêm thông tin trả lời người gọi.
          </p>
        </>
      )}
    </div>
  );
}

export function KbTable({ documents }: { documents: KbDocumentSummary[] }) {
  return (
    <div className="rounded-xl border border-border bg-card">
      <Table className="text-base">
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-12 px-4">Tiêu đề</TableHead>
            <TableHead className="hidden h-12 px-4 md:table-cell">
              Chỉ mục
            </TableHead>
            <TableHead className="hidden h-12 px-4 md:table-cell">
              Cập nhật
            </TableHead>
            <TableHead className="h-12 px-4">
              <span className="sr-only">Thao tác</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((document) => (
            <TableRow key={document.id}>
              <TableCell className="w-full px-4 py-3 whitespace-normal">
                <p className="font-medium break-words">{document.title}</p>
                {document.source && (
                  <p className="text-sm wrap-anywhere text-muted-foreground">
                    {document.source}
                  </p>
                )}
                <p className="text-sm text-muted-foreground md:hidden">
                  {document.chunk_count} đoạn · {formatDate(document.updated_at)}
                </p>
              </TableCell>
              <TableCell className="hidden px-4 md:table-cell">
                {document.chunk_count} đoạn
              </TableCell>
              <TableCell className="hidden px-4 md:table-cell">
                {formatDate(document.updated_at)}{" "}
                <span className="text-muted-foreground">
                  {formatTime(document.updated_at)}
                </span>
              </TableCell>
              <TableCell className="px-4">
                <div className="flex justify-end gap-2">
                  <EditDocumentDialog id={document.id} title={document.title} />
                  <DeleteDocumentButton
                    id={document.id}
                    title={document.title}
                  />
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
