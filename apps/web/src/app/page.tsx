"use client";

import Link from "next/link";
import { Brand } from "@/components/Brand";
import { LanguageToggle } from "@/components/LanguageToggle";
import { useUiLanguage } from "@/lib/ui-language";

const COPY = {
  en: {
    signIn: "Team sign in",
    eyebrow: "Udon Thani Lawyer · Private consultations",
    headline: "Confidential advice.",
    accent: "Clearly understood.",
    intro: "A secure consultation space for UdonLaw. Our English- and Thai-speaking legal team can meet clients with clear, private live interpretation.",
    workspace: "Enter internal workspace",
    timeLimit: "Confidential · No recording · 60-minute limit",
    consultation: "Private legal consultation",
    participants: "3 participants · Live",
    ready: "Interpreter ready",
    englishSpeaker: "UdonLaw lawyer",
    thaiSpeaker: "Thai legal team",
    client: "Client",
    translated: "Confidential English ↔ Thai interpretation",
    portal: "Private internal legal meeting system",
  },
  th: {
    signIn: "เข้าสู่ระบบทีม",
    eyebrow: "อุดรลอว์ · การปรึกษากฎหมายส่วนตัว",
    headline: "คำปรึกษาที่เป็นความลับ",
    accent: "เข้าใจกันอย่างชัดเจน",
    intro: "พื้นที่ปรึกษาที่ปลอดภัยสำหรับอุดรลอว์ ทีมกฎหมายภาษาอังกฤษและภาษาไทยสามารถพูดคุยกับลูกค้าพร้อมการแปลสดที่ชัดเจนและเป็นส่วนตัว",
    workspace: "เข้าสู่ระบบภายใน",
    timeLimit: "เป็นความลับ · ไม่บันทึกเสียง · จำกัด 60 นาที",
    consultation: "การปรึกษากฎหมายส่วนตัว",
    participants: "ผู้เข้าร่วม 3 คน · กำลังประชุม",
    ready: "ล่ามพร้อมใช้งาน",
    englishSpeaker: "ทนายความอุดรลอว์",
    thaiSpeaker: "ทีมกฎหมายภาษาไทย",
    client: "ลูกค้า",
    translated: "ล่ามภาษาอังกฤษ ↔ ไทยแบบเป็นความลับ",
    portal: "ระบบประชุมกฎหมายภายในแบบส่วนตัว",
  },
} as const;

export default function Home() {
  const { language, setLanguage } = useUiLanguage();
  const copy = COPY[language];

  return (
    <main className="app-shell flex min-h-screen flex-col">
      <div className="law-topbar -mx-5 -mt-6 mb-6 px-5 py-2.5 sm:-mx-8 sm:px-8 lg:-mx-10 lg:px-10"><div className="mx-auto flex max-w-6xl items-center justify-between gap-4 text-[11px] font-medium"><span>info@udonthanilawyer.com</span><span className="text-right uppercase tracking-[0.14em]">{copy.portal}</span></div></div>
      <header className="law-office-rule mx-auto flex w-full max-w-6xl items-center justify-between gap-3 border-b pb-5">
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
            <span className="law-accent-text">{copy.accent}</span>
          </h1>
          <p className="mt-7 max-w-xl text-lg leading-8 text-slate-400">{copy.intro}</p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link href="/login" className="primary-button !px-6">{copy.workspace} <span aria-hidden>→</span></Link>
            <span className="px-3 text-sm text-slate-500">{copy.timeLimit}</span>
          </div>
        </div>

        <div className="glass-panel law-photo-panel animate-lift-in relative overflow-hidden rounded-[1.4rem] p-5 [animation-delay:120ms] sm:p-7">
          <div className="absolute -right-16 -top-16 h-44 w-44 rounded-full bg-[#aa7d61]/20 blur-3xl" />
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
            <div className="aspect-[4/3] rounded-2xl border border-[#c79577]/40 bg-gradient-to-br from-[#293047] to-slate-900 p-3">
              <span className="rounded-lg bg-black/30 px-2 py-1 text-[10px] text-slate-300">{copy.thaiSpeaker}</span>
            </div>
          </div>
          <div className="relative mx-auto -mt-4 w-[90%] rounded-2xl border border-white/10 bg-slate-950/90 p-4 text-center shadow-2xl">
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-300">{copy.client}</span>
            <p className="mt-1 text-sm font-medium text-white">เราสามารถเริ่มโครงการได้ในวันอังคาร</p>
          </div>
          <div className="mt-4 flex items-center justify-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 rounded-full bg-[#c79577] shadow-[0_0_12px_rgba(199,149,119,.8)]" />
            {copy.translated}
          </div>
        </div>
      </section>
    </main>
  );
}
