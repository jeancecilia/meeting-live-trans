import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LumaMeet — English & Thai / การประชุมภาษาอังกฤษและไทย",
  description: "Private English ↔ Thai video meetings with real-time translated captions / วิดีโอคอลภาษาอังกฤษและไทยพร้อมคำบรรยายแปลสดแบบส่วนตัว",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
