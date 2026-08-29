import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TW Market Radar",
  description: "Taiwan sector rotation dashboard preview",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
