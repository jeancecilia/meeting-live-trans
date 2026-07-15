"use client";

import Link from "next/link";
import Image from "next/image";
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

        <div className="animate-lift-in relative aspect-[4/5] overflow-hidden rounded-[1.4rem] border border-[#aa7d61]/35 bg-white shadow-[0_28px_70px_rgba(41,48,71,0.20)] [animation-delay:120ms] lg:aspect-[4/3]">
          <Image
            src="/lawyer-nam-certification.jpeg"
            alt={language === "th" ? "ทนายความอุดรลอว์ในพิธีอบรมวิชาชีพกฎหมาย" : "UdonLaw lawyer at a professional legal certification ceremony"}
            fill
            priority
            unoptimized
            sizes="(min-width: 1024px) 42vw, 100vw"
            className="object-cover object-[center_43%]"
          />
        </div>
      </section>
    </main>
  );
}
