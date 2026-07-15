"use client";

import { useCallback, useEffect, useState } from "react";

export type UiLanguage = "en" | "th";

const STORAGE_KEY = "ui_language";
const CHANGE_EVENT = "lumameet-language-change";

function isUiLanguage(value: string | null): value is UiLanguage {
  return value === "en" || value === "th";
}

export function languageFromAccessToken(token: string): UiLanguage {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return payload.role === "internal_partner" ? "th" : "en";
  } catch {
    return "en";
  }
}

export function saveUiLanguage(language: UiLanguage) {
  localStorage.setItem(STORAGE_KEY, language);
  document.documentElement.lang = language;
  window.dispatchEvent(new CustomEvent<UiLanguage>(CHANGE_EVENT, { detail: language }));
}

export function useUiLanguage(defaultLanguage: UiLanguage = "en") {
  const [language, setLanguageState] = useState<UiLanguage>(defaultLanguage);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    const initial = isUiLanguage(stored)
      ? stored
      : navigator.language.toLowerCase().startsWith("th")
        ? "th"
        : defaultLanguage;
    setLanguageState(initial);
    document.documentElement.lang = initial;

    const onLanguageChange = (event: Event) => {
      const next = (event as CustomEvent<UiLanguage>).detail;
      if (isUiLanguage(next)) setLanguageState(next);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY && isUiLanguage(event.newValue)) setLanguageState(event.newValue);
    };
    window.addEventListener(CHANGE_EVENT, onLanguageChange);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(CHANGE_EVENT, onLanguageChange);
      window.removeEventListener("storage", onStorage);
    };
  }, [defaultLanguage]);

  const setLanguage = useCallback((next: UiLanguage) => {
    setLanguageState(next);
    saveUiLanguage(next);
  }, []);

  return { language, setLanguage };
}
