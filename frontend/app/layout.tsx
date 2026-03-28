import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniDrop AI",
  description: "AI-powered document ingestion and analytics",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
