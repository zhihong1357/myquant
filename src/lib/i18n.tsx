import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

export type Language = 'zh' | 'en';

interface I18nContextValue {
  lang: Language;
  setLang: (next: Language) => void;
  toggleLang: () => void;
  bi: (zh: string, en: string) => string;
}

const STORAGE_KEY = 'myquant_ui_lang_v1';

const I18nContext = createContext<I18nContextValue | null>(null);

function readInitialLanguage(): Language {
  if (typeof window === 'undefined') return 'zh';
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === 'en' || saved === 'zh') return saved;
  } catch {
    // Ignore storage errors inside restricted iframes
  }
  return 'zh';
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Language>(readInitialLanguage);

  const setLang = (next: Language) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Ignore storage errors
    }
  };

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    }
  }, [lang]);

  const value = useMemo<I18nContextValue>(
    () => ({
      lang,
      setLang,
      toggleLang: () => setLang(lang === 'zh' ? 'en' : 'zh'),
      bi: (zh: string, en: string) => (lang === 'zh' ? zh : en),
    }),
    [lang]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error('useI18n must be used within a LanguageProvider');
  }
  return ctx;
}
