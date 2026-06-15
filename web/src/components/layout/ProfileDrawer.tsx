import { createPortal } from 'react-dom';
import { useAuth } from '@/auth/AuthProvider';
import { useUserProfile } from '@/hooks/queries';
import { PersonIcon } from '@/components/ui/icons';
import { MaskIcon } from '@/components/ui/MaskIcon';
import { Avatar } from '@/components/ui/Avatar';

// Port of the mobile ProfileDrawer: a left drawer (2/3 width) with the user's
// avatar, email and credits, and a Log out action pinned to the bottom.
export function ProfileDrawer({
  open,
  onClose,
  onLogout,
}: {
  open: boolean;
  onClose: () => void;
  onLogout: () => void;
}) {
  const { user } = useAuth();
  const { data: profile } = useUserProfile();

  return createPortal(
    <div
      className={`fixed inset-0 z-50 ${open ? '' : 'pointer-events-none'}`}
      aria-hidden={!open}
    >
      <div
        className={`absolute inset-0 bg-black/50 transition-opacity ${open ? 'opacity-100' : 'opacity-0'}`}
        onClick={onClose}
      />
      <div
        className={`absolute inset-y-0 left-0 flex w-2/3 flex-col bg-background transition-transform duration-200 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-6 pt-8">
          <div className="flex h-[50px] w-[50px] items-center justify-center overflow-hidden rounded-full bg-surface1 text-textSecondary">
            <Avatar
              src={user?.photoURL}
              className="h-full w-full object-cover"
              fallback={<PersonIcon size={28} />}
            />
          </div>
          <p className="mt-4 text-base font-semibold text-textPrimary">
            {profile?.email ?? 'No email'}
          </p>
          <p className="mt-2 text-sm font-medium text-textSecondary">
            Credits: {profile?.credits ?? '...'}
          </p>
        </div>

        <div className="flex-1" />
        <div className="h-px bg-surface1" />
        <button
          type="button"
          onClick={() => {
            onClose();
            onLogout();
          }}
          className="flex items-center gap-3 px-6 py-5 text-left text-textPrimary"
        >
          <MaskIcon src="/icons/logout_icon.svg" size={22} color="var(--color-textPrimary)" />
          <span className="text-base font-medium">Log out</span>
        </button>
      </div>
    </div>,
    document.body,
  );
}
