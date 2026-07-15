import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LumaMeet — English & Thai meetings",
  description: "Private English ↔ Thai video meetings with real-time translated captions",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
