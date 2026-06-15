import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

// Centered modal with a dim barrier, matching Flutter's showDialog usage.
export function Modal({
  open,
  onClose,
  children,
  width = 430,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  width?: number;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full rounded-[30px] bg-surface1 p-5 border-1 border-surface2"
        style={{ maxWidth: width }}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
