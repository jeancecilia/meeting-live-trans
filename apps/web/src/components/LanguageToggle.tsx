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
      className={`language-toggle inline-flex items-center rounded-lg border p-1 ${compact ? "text-[11px]" : "text-xs"}`}
      role="group"
      aria-label={language === "th" ? "เลือกภาษา" : "Choose language"}
    >
      {(["en", "th"] as const).map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => onChange(option)}
          aria-pressed={language === option}
          className={`rounded-md font-semibold transition ${compact ? "px-2 py-1.5" : "px-3 py-2"} ${
            language === option ? "language-toggle-active shadow-sm" : "language-toggle-inactive"
          }`}
        >
          {option === "en" ? "EN" : "ไทย"}
        </button>
      ))}
    </div>
  );
}
