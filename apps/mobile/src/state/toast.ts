import { create } from 'zustand';

type Toast = { id: number; text: string };

type ToastState = { toasts: Toast[]; show: (text: string, ms?: number) => void; dismiss: (id: number) => void };

let seq = 0;

/** Short messages above the tab bar ("Rest done. Next set.", "Badge earned: First Blood"). */
export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  show: (text, ms = 3_000) => {
    const id = ++seq;
    set({ toasts: [...get().toasts.slice(-2), { id, text }] });
    setTimeout(() => get().dismiss(id), ms);
  },
  dismiss: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}));

export const toast = (text: string, ms?: number) => useToasts.getState().show(text, ms);
