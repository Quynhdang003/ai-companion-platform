import Link from "next/link";

export function CtaBanner({
  title,
  description,
  href,
  action,
}: {
  title: string;
  description: string;
  href: string;
  action: string;
}) {
  return (
    <section className="px-6 pt-20 pb-24">
      <div className="relative mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-7 overflow-hidden rounded-[2rem] bg-grad-deep px-12 py-14 text-card max-sm:px-7 max-sm:py-10">
        <div
          aria-hidden
          className="absolute -top-[140px] -right-[120px] size-[420px] rounded-full bg-grad-glow"
        />
        <div className="relative min-w-0 flex-[1_1_420px]">
          <h2 className="text-[clamp(26px,3vw,36px)] leading-tight font-bold">
            {title}
          </h2>
          <p className="mt-2 text-[17px] opacity-90">{description}</p>
        </div>
        <Link
          href={href}
          className="relative inline-flex h-14 items-center rounded-full bg-card px-7 text-[17px] font-bold text-accent-deep hover:bg-accent-soft"
        >
          {action}
        </Link>
      </div>
    </section>
  );
}
