import { PublicFooter } from "@/components/public/public-footer";

export default function PublicLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <div className="flex flex-1 flex-col">{children}</div>
      <PublicFooter />
    </>
  );
}
