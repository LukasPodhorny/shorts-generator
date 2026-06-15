import { useToastStore } from '@/store/toastStore';

// Bottom-centered snackbars, dark style matching the Material SnackBar the
// Flutter app used.
export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-center gap-2 p-4">
      {toasts.map((t) => (
        <button
          key={t.id}
          onClick={() => dismiss(t.id)}
          className="pointer-events-auto max-w-md rounded-lg bg-surface3 px-4 py-3 text-left text-sm text-textPrimary shadow-lg shadow-black/40"
        >
          {t.message}
        </button>
      ))}
    </div>
  );
}
