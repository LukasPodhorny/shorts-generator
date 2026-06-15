import { create } from 'zustand';

// Lightweight replacement for Flutter's ScaffoldMessenger.showSnackBar.
export interface Toast {
  id: number;
  message: string;
}

interface ToastState {
  toasts: Toast[];
  show: (message: string) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  show: (message) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, message }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 4000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** Imperative helper usable outside React (mirrors showSnackBar call sites). */
export const toast = (message: string) => useToastStore.getState().show(message);
