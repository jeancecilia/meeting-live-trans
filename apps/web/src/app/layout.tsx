import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UdonLaw Meetings — Private Legal Consultations / การปรึกษากฎหมายส่วนตัว",
  description: "Private English ↔ Thai legal consultations for UdonLaw / การปรึกษากฎหมายภาษาอังกฤษและไทยแบบส่วนตัวสำหรับอุดรลอว์",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
