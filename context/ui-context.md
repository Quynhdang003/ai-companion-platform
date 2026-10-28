# UI Context

## Brand

Display name **Touch the Light** (site title, headers, footer); logo = Lucide `Sun` in a `bg-grad-brand` tile (`components/brand-logo.tsx`). Repo/code names stay `ai-companion`.

## Theme

Light mode only. Calm, warm and trustworthy design for family members (often middle-aged, non-technical): white surfaces on soft warm background, generous spacing, large readable text, clear status colors for scam alerts. Vietnamese UI copy.

## Colors

Use these CSS tokens only; no hardcoded hex.

| Role | Variable | Value |
|---|---|---|
| Page background | `--bg-base` | `#F7F5F2` |
| Surface | `--bg-surface` | `#FFFFFF` |
| Primary text | `--text-primary` | `#1F2937` |
| Muted text | `--text-muted` | `#6B7280` |
| Primary accent | `--accent-primary` | `#0F766E` |
| Border | `--border-default` | `#E5E1DA` |
| Error / high risk | `--state-error` | `#DC2626` |
| Warning / medium risk | `--state-warning` | `#D97706` |
| Success | `--state-success` | `#16A34A` |

### Derived tokens

Defined in `globals.css` with `color-mix()` from the base tokens (no new hex). Exposed as Tailwind colors (`bg-accent-soft`, `text-error-text`, …) or custom utilities.

| Token | Tailwind | Use |
|---|---|---|
| `--accent-soft` | `bg-accent-soft` | Elder chat bubbles, light accent fills |
| `--accent-mid`, `--accent-deep` | `text-accent-deep` … | Gradient stops; text on white buttons over gradients |
| `--{error,warning,success}-soft` | `bg-error-soft` … | Status badge / step fills |
| `--{error,warning,success}-text` | `text-error-text` … | Status text on soft fills |
| `--error-border` | `border-error-border` | Border of a warning chat bubble |
| `--grad-brand` | `bg-grad-brand` | Logo, icon tiles, active tab, primary CTA |
| `--grad-deep` | `bg-grad-deep` | Highlight card, CTA banner |
| `--grad-text` | `text-gradient` | Highlighted words in hero headings |
| `--grad-risk` | `bg-grad-risk` | Scam risk bar (low → high) |
| `--grad-hero` | `bg-hero` | Public page hero background |
| `--grad-glow` | `bg-grad-glow` | Decorative glow in the CTA banner |
| `--shadow-card`, `--shadow-pill` | `shadow-card`, `shadow-pill` | Raised cards; active nav item |

## Typography

| Role | Font | Variable |
|---|---|---|
| UI text | Be Vietnam Pro (next/font) | `--font-sans` |
| Code/mono | Geist Mono | `--font-mono` |

Base size 16px; body text never below 14px. Weights 400–800; 800 only for public hero headings.

## Border radius

| Context | Class |
|---|---|
| Inline / small UI | `rounded-md` |
| Card / panel | `rounded-xl` |
| Modal / overlay | `rounded-2xl` |
| Public pages: card / panel | `rounded-3xl` |
| Public pages: buttons, nav, tabs, badges | `rounded-full` |
| Public pages: icon tile | `rounded-xl` (logo) / `rounded-2xl` (48px tile) |
| Public pages: CTA banner | `rounded-[2rem]` |

## Component library

shadcn/ui on Tailwind, in `components/ui/`. Add components via shadcn CLI, don't hand-write.

## Layout patterns

- Public pages (`app/(public)/`: `/`, `/demo`, `/sign-in`, `/sign-up`): each page starts with `<PublicHero current=…>` (`bg-hero` + `PublicHeader`: logo, pill nav, account actions); the group layout adds `PublicFooter`. Container `max-w-[1200px] px-6`; nav wraps to its own centered row below 900px; tap targets ≥ 44px. Components in `components/public/`.
- Landing page: hero (eyebrow, heading with `text-gradient` words, register + demo CTAs), how it works (call → AI companion → family alerts) on a white band, `CtaBanner`.
- Demo page: hero, two overlapping cards (demo hotline, web call), white band with scenario tabs (chat transcript + "Phía sau cuộc gọi" steps, risk bar for scam), `CtaBanner`.
- Sign-in / sign-up: Clerk form centered inside `PublicHero`.
- Dashboard: left sidebar (fixed width, right border) + main content; collapses to top nav on mobile.
- Elder detail: profile card, call history list, scam alerts with risk badge.
- Navbar (dashboard/admin): top bar with bottom border, brand logo, user menu (Clerk).
- Dashboard (current, before the sidebar): page title + primary action, sections "Yêu cầu chờ bạn duyệt" (only when any), "Người thân của bạn" (card grid, dashed empty state), "Yêu cầu bạn đã gửi". Status badges are `rounded-full` pills on the soft tokens (`bg-warning-soft text-warning-text`, …), 14px text. shadcn controls default to 32px / 12–14px; pass `h-11 text-base` so inputs and buttons stay ≥ 44px and ≥ 16px.
- Forms: centered `max-w-xl` card, shadcn `Field` + `FieldLabel` + `FieldDescription` + `FieldError`; backend error codes map to field errors, anything else to a toast.
- Modal: centered overlay with backdrop blur.
- Admin: tables for KB documents and scam patterns with search and CRUD dialogs.

## Icons

Lucide React, stroke icons only. Size: `h-4 w-4` inline, `h-5 w-5` buttons.
