import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Mic, Phone } from "lucide-react";
import { CtaBanner } from "@/components/public/cta-banner";
import { DemoScenarios } from "@/components/public/demo-scenarios";
import { PublicHero } from "@/components/public/public-hero";

export const metadata: Metadata = { title: "Demo" };

// No public hotline yet: calls are web-simulated until real telephony is set up.
const demoPhoneNumber = process.env.NEXT_PUBLIC_DEMO_PHONE_NUMBER;

export default function DemoPage() {
  return (
    <main>
      <PublicHero current="/demo">
        <section className="mx-auto flex max-w-[1200px] flex-col items-center gap-[22px] px-6 pt-12 pb-[72px] text-center">
          <span className="text-sm font-bold tracking-[0.08em] text-primary uppercase">
            Demo
          </span>
          <h1 className="max-w-[880px] text-[clamp(36px,4.8vw,58px)] leading-[1.1] font-extrabold tracking-[-0.025em]">
            Nghe thử trợ lý{" "}
            <span className="text-gradient">trò chuyện với ông bà</span>
          </h1>
          <p className="max-w-[640px] text-[19px] text-muted-foreground">
            Chọn một kịch bản bên dưới để xem trợ lý nói gì và hệ thống làm gì
            phía sau. Hoặc tự gọi thử để nghe bằng chính tai mình.
          </p>
        </section>
      </PublicHero>

      <section className="mx-auto -mt-6 grid max-w-[1200px] grid-cols-[repeat(auto-fit,minmax(min(320px,100%),1fr))] gap-5 px-6 pb-20">
        <div className="flex flex-col gap-3.5 rounded-3xl border border-border bg-card p-7 shadow-card">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-grad-brand text-card">
            <Phone className="size-[22px]" aria-hidden />
          </span>
          <h2 className="text-[22px] font-bold">Gọi tổng đài demo</h2>
          <p className="text-muted-foreground">
            Gọi từ bất kỳ điện thoại nào. Số chưa đăng ký nên bạn sẽ nghe lời
            chào chung — đúng như một người lạ gọi vào.
          </p>
          {demoPhoneNumber ? (
            <span className="font-mono text-[26px] font-medium tracking-[0.02em]">
              {demoPhoneNumber}
            </span>
          ) : (
            <span className="text-lg font-semibold text-muted-foreground">
              Sắp ra mắt
            </span>
          )}
        </div>

        <div className="flex flex-col gap-3.5 rounded-3xl bg-grad-deep p-7 text-card shadow-card">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-card/20">
            <Mic className="size-[22px]" aria-hidden />
          </span>
          <h2 className="text-[22px] font-bold">Gọi thử trên web</h2>
          <p className="opacity-90">
            Đăng nhập rồi gọi bằng micro máy tính, đóng vai chính người thân
            bạn đã đăng ký — trợ lý sẽ chào đúng tên và nhớ chuyện cũ.
          </p>
          {/* Points at the dashboard until the web call page exists. */}
          <Link
            href="/dashboard"
            className="inline-flex h-12 items-center gap-2 self-start rounded-full bg-card px-[22px] font-bold text-accent-deep hover:bg-accent-soft"
          >
            Mở trang gọi thử
            <ArrowRight className="size-[18px]" aria-hidden />
          </Link>
        </div>
      </section>

      <section className="border-y border-border bg-card">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-[18px] px-6 py-[88px] max-sm:py-16">
          <h2 className="text-center text-[clamp(28px,3.2vw,40px)] leading-tight font-bold tracking-[-0.02em]">
            Ba kịch bản tiêu biểu
          </h2>
          <DemoScenarios />
        </div>
      </section>

      <CtaBanner
        title="Sẵn sàng cho ông bà dùng thật?"
        description="Đăng ký chỉ với họ tên và số điện thoại."
        href="/dashboard/elders/new"
        action="Đăng ký cho người thân"
      />
    </main>
  );
}
