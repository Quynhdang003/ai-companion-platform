import type { Metadata } from "next";
import { Be_Vietnam_Pro, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { viVN } from "@clerk/localizations";
import "./globals.css";

const beVietnamPro = Be_Vietnam_Pro({
  variable: "--font-sans",
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: { default: "Touch the Light", template: "%s · Touch the Light" },
  description:
    "Trợ lý giọng nói trò chuyện với người thân của bạn, nhớ chuyện cũ, giúp việc hằng ngày và cảnh báo lừa đảo cho cả gia đình.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="vi"
      className={`${beVietnamPro.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ClerkProvider
          localization={viVN}
          appearance={{
            variables: {
              colorPrimary: "var(--accent-primary)",
              fontFamily: "var(--font-sans)",
            },
          }}
        >
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
