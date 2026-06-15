import { Modal } from '@/components/ui/Modal';
import { DialogPillButton } from '@/components/ui/DialogPillButton';

// Port of the Flutter logout confirmation dialog.
export function LogoutDialog({
  open,
  onClose,
  onConfirm,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose}>
      <div className="flex flex-col">
        <h2 className="text-[17px] font-semibold text-textPrimary">Log out</h2>
        <p className="mt-3 text-[15px] text-textSecondary">Are you sure you want to log out?</p>
        <div className="mt-5 flex justify-end gap-1">
          <DialogPillButton
            label="Cancel"
            hoverBackground="var(--color-surface2)"
            textColor="var(--color-textSecondary)"
            onClick={onClose}
          />
          <DialogPillButton
            label="Log out"
            hoverBackground="var(--color-surface3)"
            textColor="var(--color-accentRed)"
            onClick={() => {
              onClose();
              onConfirm();
            }}
          />
        </div>
      </div>
    </Modal>
  );
}
