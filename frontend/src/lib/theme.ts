import { create } from "zustand";

type Theme = "light" | "dark";

type ThemeStore = {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
};

function readInitial(): Theme {
  if (typeof window === "undefined") return "light";
  try {
    const t = localStorage.getItem("jobforge.theme");
    if (t === "dark" || t === "light") return t;
  } catch {
    // ignore
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(t: Theme) {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", t === "dark");
  try {
    localStorage.setItem("jobforge.theme", t);
  } catch {
    // ignore
  }
}

export const useThemeStore = create<ThemeStore>((set, get) => ({
  theme: readInitial(),
  setTheme: (t) => {
    applyTheme(t);
    set({ theme: t });
  },
  toggle: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    set({ theme: next });
  },
}));
