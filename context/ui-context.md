# UI Context

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

## Typography

| Role | Font | Variable |
|---|---|---|
| UI text | Be Vietnam Pro (next/font) | `--font-sans` |
| Code/mono | Geist Mono | `--font-mono` |

Base size 16px; body text never below 14px.

## Border radius

| Context | Class |
|---|---|
| Inline / small UI | `rounded-md` |
| Card / panel | `rounded-xl` |
| Modal / overlay | `rounded-2xl` |

## Component library

shadcn/ui on Tailwind, in `components/ui/`. Add components via shadcn CLI, don't hand-write.

## Layout patterns

- Landing page: hero, how it works (call → AI companion → family alerts), register CTA.
- Dashboard: left sidebar (fixed width, right border) + main content; collapses to top nav on mobile.
- Elder detail: profile card, call history list, scam alerts with risk badge.
- Navbar: top bar with bottom border, user menu (Clerk).
- Modal: centered overlay with backdrop blur.
- Admin: tables for KB documents and scam patterns with search and CRUD dialogs.

## Icons

Lucide React, stroke icons only. Size: `h-4 w-4` inline, `h-5 w-5` buttons.
