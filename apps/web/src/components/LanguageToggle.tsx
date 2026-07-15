"use client";

import type { UiLanguage } from "@/lib/ui-language";

export function LanguageToggle({
  language,
  onChange,
  compact = false,
}: {
  language: UiLanguage;
  onChange: (language: UiLanguage) => void;
  compact?: boolean;
}) {
  return (
    <div
      className={`inline-flex items-center rounded-xl border border-white/10 bg-slate-950/55 p-1 ${compact ? "text-[11px]" : "text-xs"}`}
      role="group"
      aria-label={language === "th" ? "เลือกภาษา" : "Choose language"}
    >
      {(["en", "th"] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={language === option}
          className={`rounded-lg font-semibold transition ${compact ? "px-2 py-1.5" : "px-3 py-2"} ${
            language === option ? "bg-white/10 text-white shadow-sm" : "text-slate-500 hover:text-slate-300"
          }`}
        >
          {option === "en" ? "EN" : "ไทย"}
        </button>
      ))}
    </div>
  );
}
