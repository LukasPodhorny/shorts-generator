import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { useUserProfile } from '@/hooks/queries';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { PersonIcon } from '@/components/ui/icons';
import { Avatar } from '@/components/ui/Avatar';

// Port of the mobile TopBar: profile avatar (opens drawer), a generate/videos
// segmented toggle, and the credit count.
export function MobileTopBar({ onOpenDrawer }: { onOpenDrawer: () => void }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { data: profile } = useUserProfile();
  const isGenerate = pathname === '/';

  return (
    <div className="px-[18px] pt-2.5">
      <div className="flex h-[50px] items-center justify-between">
        <button
          type="button"
          onClick={onOpenDrawer}
          className="flex h-[42px] w-[42px] items-center justify-center overflow-hidden rounded-full bg-surface1 text-textSecondary"
          aria-label="Open menu"
        >
          <Avatar
            src={user?.photoURL}
            className="h-full w-full object-cover"
            fallback={<PersonIcon size={24} />}
          />
        </button>

        <div className="flex h-10 w-[184px] overflow-hidden rounded-3xl">
          {(['generate', 'videos'] as const).map((tab) => {
            const active = tab === 'generate' ? isGenerate : !isGenerate;
            return (
              <button
                key={tab}
                type="button"
                onClick={() => navigate(tab === 'generate' ? '/' : '/videos')}
                className={`flex flex-1 items-center justify-center rounded-3xl text-base font-semibold tracking-[0.3px] text-textPrimary ${
                  active ? 'bg-surface2' : 'bg-transparent'
                }`}
              >
                {tab}
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-[5px] pr-1">
          <span className="text-base font-bold text-textPrimary">{profile?.credits ?? '...'}</span>
          <CreditIcon size={12} color="var(--color-textPrimary)" />
        </div>
      </div>
    </div>
  );
}
