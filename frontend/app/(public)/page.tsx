import Link from "next/link";
import { ArrowRight, Bell, MessageCircle, Phone } from "lucide-react";
import { CtaBanner } from "@/components/public/cta-banner";
import { PublicHero } from "@/components/public/public-hero";

const steps = [
  {
    icon: Phone,
    title: "Người thân của bạn gọi điện",
    description:
      "Gọi vào số tổng đài từ bất kỳ điện thoại nào. Trợ lý nhận ra số đã đăng ký và chào đúng tên.",
  },
  {
    icon: MessageCircle,
    title: "Trợ lý trò chuyện, giúp việc",
    description:
      "Nhớ chuyện từ những cuộc gọi trước, trả lời thời tiết, tin tức, đặt xe đi khám. Việc quan trọng luôn hỏi lại trước khi làm.",
  },
  {
    icon: Bell,
    title: "Người thân được báo tin",
    description:
      "Thấy dấu hiệu lừa đảo, trợ lý cảnh báo người thân của bạn ngay và nhắn Telegram cho gia đình. Sau mỗi cuộc gọi có bản tóm tắt để xem lại.",
  },
];

export default function Home() {
  return (
    <main>
      <PublicHero current="/">
        <section className="mx-auto flex max-w-[1200px] flex-col items-center gap-[22px] px-6 pt-12 pb-[88px] text-center">
          <span className="text-sm font-bold tracking-[0.08em] text-primary uppercase">
            Trợ lý giọng nói cho người cao tuổi
          </span>
          <h1 className="max-w-[880px] text-[clamp(36px,4.8vw,58px)] leading-[1.1] font-extrabold tracking-[-0.025em]">
            Một cuộc gọi, <span className="text-gradient">có người bầu bạn</span>
          </h1>
          <p className="max-w-[640px] text-[19px] text-muted-foreground">
            Người thân của bạn không cần điện thoại thông minh hay ứng dụng, chỉ
            cần gọi điện. Trợ lý trò chuyện, nhớ chuyện cũ, giúp việc hằng ngày
            và cảnh báo khi có dấu hiệu lừa đảo.
          </p>
          <div className="mt-2 flex flex-wrap justify-center gap-3">
            <Link
              href="/dashboard/elders/new"
              className="inline-flex h-14 items-center rounded-full bg-grad-brand px-7 text-[17px] font-bold text-card shadow-card"
            >
              Đăng ký cho người thân
            </Link>
            <Link
              href="/demo"
              className="inline-flex h-14 items-center gap-2 rounded-full border border-border bg-card px-7 text-[17px] font-semibold text-foreground hover:text-primary"
            >
              Xem demo
              <ArrowRight className="size-[18px]" aria-hidden />
            </Link>
          </div>
        </section>
      </PublicHero>

      <section className="border-y border-border bg-card">
        <div className="mx-auto flex max-w-[1200px] flex-col gap-8 px-6 py-[88px] max-sm:py-16">
          <h2 className="text-center text-[clamp(28px,3.2vw,40px)] leading-tight font-bold tracking-[-0.02em]">
            Cách hoạt động
          </h2>
          <ol className="grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-5">
            {steps.map((step, index) => (
              <li
                key={step.title}
                className="flex flex-col gap-3.5 rounded-3xl bg-background p-7"
              >
                <span className="flex size-12 items-center justify-center rounded-2xl bg-grad-brand text-card">
                  <step.icon className="size-[22px]" aria-hidden />
                </span>
                <span className="text-sm font-bold tracking-[0.08em] text-primary uppercase">
                  Bước {index + 1}
                </span>
                <h3 className="text-[22px] font-bold">{step.title}</h3>
                <p className="text-muted-foreground">{step.description}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <CtaBanner
        title="Đăng ký cho người thân ngay hôm nay"
        description="Chỉ cần họ tên và số điện thoại. Lần gọi đầu tiên, trợ lý sẽ xin phép người thân của bạn trước khi bắt đầu."
        href="/dashboard/elders/new"
        action="Đăng ký cho người thân"
      />
    </main>
  );
}
