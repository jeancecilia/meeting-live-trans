"use client";

import Link from "next/link";
import { Brand } from "@/components/Brand";
import { LanguageToggle } from "@/components/LanguageToggle";
import { useUiLanguage } from "@/lib/ui-language";

const COPY = {
  en: {
    signIn: "Internal sign in",
    eyebrow: "Private bilingual meetings",
    headline: "Speak naturally.",
    accent: "Understand instantly.",
    intro: "Secure English and Thai video calls with live, private translation for your internal team. Clients join from one simple link—no account required.",
    workspace: "Open your workspace",
    timeLimit: "Calls end automatically after 60 minutes",
    consultation: "Client consultation",
    participants: "3 participants · Live",
    ready: "Translation ready",
    englishSpeaker: "English speaker",
    thaiSpeaker: "Thai speaker",
    client: "Client",
    translated: "Separate, private audio translation",
  },
  th: {
    signIn: "เข้าสู่ระบบสำหรับทีม",
    eyebrow: "การประชุมสองภาษาแบบส่วนตัว",
    headline: "พูดได้อย่างเป็นธรรมชาติ",
    accent: "เข้าใจกันได้ทันที",
    intro: "วิดีโอคอลภาษาอังกฤษและภาษาไทยที่ปลอดภัย พร้อมคำแปลสดแบบส่วนตัวสำหรับทีมของคุณ ลูกค้าเข้าร่วมได้ง่าย ๆ ผ่านลิงก์เดียวโดยไม่ต้องมีบัญชี",
    workspace: "เปิดพื้นที่ทำงาน",
    timeLimit: "สายจะสิ้นสุดอัตโนมัติหลัง 60 นาที",
    consultation: "การปรึกษากับลูกค้า",
    participants: "ผู้เข้าร่วม 3 คน · กำลังประชุม",
    ready: "พร้อมแปลภาษา",
    englishSpeaker: "ผู้พูดภาษาอังกฤษ",
    thaiSpeaker: "ผู้พูดภาษาไทย",
    client: "ลูกค้า",
    translated: "แปลเสียงแยกแบบส่วนตัว",
  },
} as const;

export default function Home() {
  const { language, setLanguage } = useUiLanguage();
  const copy = COPY[language];

  return (
    <main className="app-shell flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3">
        <Brand />
        <div className="flex items-center gap-2">
          <LanguageToggle language={language} onChange={setLanguage} compact />
          <Link href="/login" className="secondary-button !px-4 !py-2.5">{copy.signIn}</Link>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-6xl flex-1 items-center gap-12 py-16 lg:grid-cols-[1.08fr_.92fr] lg:py-20">
        <div className="animate-lift-in max-w-2xl">
          <p className="eyebrow mb-5">{copy.eyebrow}</p>
          <h1 className="text-5xl font-semibold leading-[1.02] tracking-[-0.055em] text-white sm:text-6xl lg:text-7xl">
            {copy.headline}<br />
            <span className="bg-gradient-to-r from-cyan-300 via-sky-400 to-violet-400 bg-clip-text text-transparent">{copy.accent}</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-8 text-slate-400">{copy.intro}</p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link href="/login" className="primary-button !px-6">{copy.workspace} <span aria-hidden>→</span></Link>
            <span className="px-3 text-sm text-slate-500">{copy.timeLimit}</span>
          </div>
        </div>

        <div className="glass-panel animate-lift-in relative overflow-hidden rounded-[2rem] p-5 [animation-delay:120ms] sm:p-7">
          <div className="absolute -right-16 -top-16 h-44 w-44 rounded-full bg-violet-500/20 blur-3xl" />
          <div className="relative mb-5 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-white">{copy.consultation}</p>
              <p className="mt-1 text-xs text-slate-500">{copy.participants}</p>
            </div>
            <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-[11px] font-semibold text-emerald-300">{copy.ready}</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="aspect-[4/3] rounded-2xl border border-white/10 bg-gradient-to-br from-slate-700 to-slate-900 p-3">
              <span className="rounded-lg bg-black/30 px-2 py-1 text-[10px] text-slate-300">{copy.englishSpeaker}</span>
            </div>
            <div className="aspect-[4/3] rounded-2xl border border-cyan-400/30 bg-gradient-to-br from-sky-950 to-slate-900 p-3">
              <span className="rounded-lg bg-black/30 px-2 py-1 text-[10px] text-slate-300">{copy.thaiSpeaker}</span>
            </div>
          </div>
          <div className="relative mx-auto -mt-4 w-[90%] rounded-2xl border border-white/10 bg-slate-950/90 p-4 text-center shadow-2xl">
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-300">{copy.client}</span>
            <p className="mt-1 text-sm font-medium text-white">เราสามารถเริ่มโครงการได้ในวันอังคาร</p>
          </div>
          <div className="mt-4 flex items-center justify-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,.8)]" />
            {copy.translated}
          </div>
        </div>
      </section>
    </main>
  );
}
