import { create } from "zustand";

type ToastKind = "default" | "success" | "error" | "warning";

export type Toast = {
  id: number;
  title?: string;
  description?: string;
  kind: ToastKind;
};

type ToastStore = {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => number;
  dismiss: (id: number) => void;
};

let nextId = 1;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (t) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, ...t }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) }));
    }, 4500);
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));

export function toast(opts: Omit<Toast, "id" | "kind"> & { kind?: ToastKind }) {
  return useToastStore.getState().push({ kind: opts.kind ?? "default", ...opts });
}
