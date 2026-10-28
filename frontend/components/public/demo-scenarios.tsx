"use client";

import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

type Bubble = {
  kind: "bubble";
  from: "assistant" | "elder";
  text: string;
  danger?: boolean;
};
type Alert = { kind: "alert"; text: string };
type Step = { content: ReactNode; tone: "brand" | "warning" | "error" };
type Scenario = {
  id: string;
  label: string;
  items: (Bubble | Alert)[];
  steps: Step[];
  // Marker position on the risk bar, in percent.
  risk?: { position: number; label: string };
};

const scenarios: Scenario[] = [
  {
    id: "chat",
    label: "Trò chuyện hằng ngày",
    items: [
      {
        kind: "bubble",
        from: "assistant",
        text: "Chào bà Lan ạ! Hôm qua bà kể cháu Bin sắp thi Toán, thi xong chưa bà?",
      },
      {
        kind: "bubble",
        from: "elder",
        text: "Thi rồi, được 10 cháu ạ. Hôm nay trời có mưa không?",
      },
      {
        kind: "bubble",
        from: "assistant",
        text: "Giỏi quá bà ạ! Hà Nội hôm nay khoảng 24 độ, chiều mưa nhẹ. Chiều nay bà có lịch tái khám, nhớ mang ô nhé.",
      },
      { kind: "bubble", from: "elder", text: "Ừ, may cháu nhắc." },
    ],
    steps: [
      {
        tone: "brand",
        content:
          "Nhận diện số gọi đến, lấy tên gọi và tóm tắt ghi nhớ trong chưa đầy nửa giây.",
      },
      {
        tone: "brand",
        content:
          "Dùng lại chuyện “cháu Bin thi Toán” từ cuộc gọi trước để hỏi han.",
      },
      {
        tone: "brand",
        content:
          "Tra thời tiết và lời nhắc lịch khám, trả lời bằng câu ngắn dễ nghe.",
      },
      {
        tone: "brand",
        content: "Sau cuộc gọi: lưu ghi nhớ mới, gửi tóm tắt cho người thân.",
      },
    ],
  },
  {
    id: "ride",
    label: "Đặt xe “như lần trước”",
    items: [
      {
        kind: "bubble",
        from: "elder",
        text: "Cháu đặt xe cho bà đi khám như lần trước nhé.",
      },
      {
        kind: "bubble",
        from: "assistant",
        text: "Dạ, từ nhà mình ở Phố Vọng đến Bệnh viện Bạch Mai, xe 4 chỗ. Giá khoảng 68 nghìn, xe tới sau 5 phút. Bà đồng ý để cháu đặt không ạ?",
      },
      { kind: "bubble", from: "elder", text: "Ừ, cháu đặt đi." },
      {
        kind: "bubble",
        from: "assistant",
        text: "Cháu đặt rồi ạ. Tài xế Hùng, xe trắng biển 30A-123.45. Cháu đã nhắn chị Hoa biết.",
      },
    ],
    steps: [
      {
        tone: "brand",
        content: "“Như lần trước” → ghi nhớ: nhà → BV Bạch Mai, xe 4 chỗ.",
      },
      { tone: "brand", content: "Tìm địa điểm, lấy báo giá và thời gian chờ." },
      {
        tone: "warning",
        content: (
          <>
            <b>Dừng lại hỏi bà đồng ý</b> — chưa có lời “đồng ý” thì không đặt.
          </>
        ),
      },
      {
        tone: "brand",
        content: "Đặt xe, theo dõi trạng thái chuyến và báo người thân.",
      },
    ],
  },
  {
    id: "scam",
    label: "Cuộc gọi lừa đảo",
    items: [
      {
        kind: "bubble",
        from: "elder",
        text: "Có người xưng công an bảo tài khoản bà dính vụ án, phải chuyển tiền sang tài khoản tạm giữ, không được nói với ai.",
      },
      { kind: "alert", text: "Rủi ro cao · mạo danh công an" },
      {
        kind: "bubble",
        from: "assistant",
        danger: true,
        text: "Bà ơi, công an không bao giờ yêu cầu chuyển tiền qua điện thoại. Việc này rất giống lừa đảo. Bà đừng chuyển nhé. Bà có muốn cháu báo chị Hoa không ạ?",
      },
      { kind: "bubble", from: "elder", text: "Ừ, cháu báo cái Hoa giúp bà." },
    ],
    steps: [
      {
        tone: "brand",
        content:
          "Lớp 1 bắt từ khóa: “công an”, “chuyển tiền”, “không được nói”.",
      },
      {
        tone: "brand",
        content: "Lớp 2 đối chiếu mẫu lừa đảo, kết luận: rủi ro cao.",
      },
      { tone: "error", content: "Trợ lý cảnh báo bà ngay trong cuộc gọi." },
      { tone: "error", content: "Gửi Telegram cho người thân trong vài giây." },
    ],
    risk: { position: 90, label: "cao" },
  },
];

const stepTone: Record<Step["tone"], string> = {
  brand: "bg-grad-brand text-card",
  warning: "bg-warning-soft text-warning-text",
  error: "bg-error-soft text-error-text",
};

export function DemoScenarios() {
  const [activeId, setActiveId] = useState(scenarios[0].id);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const active = scenarios.find((s) => s.id === activeId) ?? scenarios[0];

  function handleKeyDown(event: KeyboardEvent, index: number) {
    const offset =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (offset === 0) return;
    event.preventDefault();
    const next = (index + offset + scenarios.length) % scenarios.length;
    setActiveId(scenarios[next].id);
    tabRefs.current[next]?.focus();
  }

  return (
    <>
      <div
        role="tablist"
        aria-label="Kịch bản"
        className="inline-flex flex-wrap justify-center gap-1 self-center rounded-full border border-border bg-background p-[5px] max-sm:w-full max-sm:flex-col max-sm:rounded-3xl"
      >
        {scenarios.map((s, index) => {
          const selected = s.id === active.id;
          return (
            <button
              key={s.id}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${s.id}`}
              aria-selected={selected}
              aria-controls={`panel-${s.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveId(s.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={cn(
                "h-11 rounded-full px-5",
                selected
                  ? "bg-grad-brand font-semibold text-card"
                  : "font-medium text-muted-foreground hover:text-foreground",
              )}
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`panel-${active.id}`}
        aria-labelledby={`tab-${active.id}`}
        className="mt-3.5 flex flex-wrap items-start gap-6"
      >
        <div className="flex min-w-0 flex-[3_1_520px] flex-col gap-3 rounded-3xl bg-background p-7 max-sm:p-5">
          {active.items.map((item, index) =>
            item.kind === "alert" ? (
              <div
                key={index}
                className="inline-flex items-center gap-1.5 self-end rounded-full bg-error-soft px-3 py-1 text-sm font-semibold text-error-text"
              >
                <TriangleAlert
                  className="size-3.5"
                  strokeWidth={2.5}
                  aria-hidden
                />
                {item.text}
              </div>
            ) : (
              <div
                key={index}
                className={cn(
                  "max-w-[82%] px-4 py-3",
                  item.from === "assistant"
                    ? "self-start rounded-[18px_18px_18px_6px] bg-card"
                    : "self-end rounded-[18px_18px_6px_18px] bg-accent-soft",
                  item.danger && "border border-error-border",
                )}
              >
                {item.text}
              </div>
            ),
          )}
        </div>

        <aside className="flex min-w-0 flex-[2_1_320px] flex-col gap-4 rounded-3xl border border-border p-[26px]">
          <h3 className="text-lg font-bold">Phía sau cuộc gọi</h3>
          {active.risk && <RiskBar {...active.risk} />}
          <ol className="flex flex-col gap-3.5 text-[15px]">
            {active.steps.map((step, index) => (
              <li key={index} className="flex gap-3">
                <span
                  className={cn(
                    "flex size-[26px] flex-none items-center justify-center rounded-full text-sm font-bold",
                    stepTone[step.tone],
                  )}
                >
                  {index + 1}
                </span>
                <span>{step.content}</span>
              </li>
            ))}
          </ol>
        </aside>
      </div>
    </>
  );
}

function RiskBar({ position, label }: { position: number; label: string }) {
  return (
    <div className="flex flex-col gap-2">
      <div
        role="img"
        aria-label={`Mức rủi ro: ${label}`}
        className="relative h-2.5 rounded-full bg-grad-risk"
      >
        <span
          className="absolute -top-1 size-[18px] -translate-x-1/2 rounded-full border-[3px] border-destructive bg-card"
          style={{ left: `${position}%` }}
        />
      </div>
      <div className="flex justify-between text-sm font-semibold">
        <span className="text-success-text">Thấp</span>
        <span className="text-error-text">Cao</span>
      </div>
    </div>
  );
}
