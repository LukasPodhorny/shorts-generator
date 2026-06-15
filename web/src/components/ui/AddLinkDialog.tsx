import { useState } from 'react';
import { Modal } from './Modal';
import { DialogPillButton } from './DialogPillButton';
import { normalizeLink } from '@/lib/sourceFiles';

// Ports _AddLinkDialog: enter a source link, returns the normalized URL via onAdd.
export function AddLinkDialog({
  open,
  onClose,
  onAdd,
}: {
  open: boolean;
  onClose: () => void;
  onAdd: (url: string) => void;
}) {
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setValue('');
    setError(null);
    onClose();
  };

  const submit = () => {
    const link = normalizeLink(value);
    if (!link) {
      setError('Enter a valid link, e.g. youtube.com/watch?v=…');
      return;
    }
    onAdd(link);
    close();
  };

  return (
    <Modal open={open} onClose={close}>
      <div className="flex flex-col">
        <h2 className="text-[17px] font-semibold text-textPrimary">Add link</h2>
        <div className="h-4" />
        <input
          autoFocus
          type="url"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (error) setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit();
          }}
          placeholder="Paste a link…"
          className="rounded-[30px] bg-surface2 focus:ring-1 ring-surface3 transition-all duration-150 px-4 py-[13px] text-[15px] text-textPrimary caret-textPrimary outline-none placeholder:text-textSecondary"
        />
        {error && <p className="mt-2 text-xs text-error">{error}</p>}
        <div className="mt-5 flex justify-end gap-1">
          <DialogPillButton
            label="Cancel"
            hoverBackground="var(--color-surface2)"
            textColor="var(--color-textSecondary)"
            onClick={close}
          />
          <DialogPillButton
            label="Add"

            hoverBackground="var(--color-surface2)"
            textColor="var(--color-textPrimary)"
            onClick={submit}
          />
        </div>
      </div>
    </Modal>
  );
}
