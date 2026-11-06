import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LMT Studio Pro V2",
  description: "AI Video & Storytelling Studio",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className="dark">
      <body>{children}</body>
    </html>
  );
}
