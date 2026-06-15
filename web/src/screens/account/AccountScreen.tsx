import { useAuth } from '@/auth/AuthProvider';
import { useUserProfile } from '@/hooks/queries';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { PersonIcon } from '@/components/ui/icons';
import { Spinner } from '@/components/ui/Spinner';
import { Avatar } from '@/components/ui/Avatar';

// Port of desktop_account_screen: profile header (avatar, credits, tier, email)
// and an "Upgrade your plan — Coming soon" section.
export default function AccountScreen() {
  const { user } = useAuth();
  const { data: profile, isLoading, isError } = useUserProfile();

  return (
    <div className="h-full overflow-y-auto p-10">
      {isLoading ? (
        <Spinner size={50} />
      ) : isError || !profile ? (
        <p className="text-error">Error loading profile</p>
      ) : (
        <div className="flex items-center gap-5">
          <div className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-full bg-surface2 text-textSecondary">
            <Avatar
              src={user?.photoURL}
              className="h-full w-full object-cover"
              fallback={<PersonIcon size={36} />}
            />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1 text-xl font-bold text-textPrimary">
                {profile.credits}
                <CreditIcon size={14} color="var(--color-textPrimary)" />
              </span>
              <span className="text-sm font-medium text-freeTierPurple">free tier</span>
            </div>
            <span className="mt-1 text-base font-medium text-textPrimary">
              {profile.email ?? 'No email'}
            </span>
          </div>
        </div>
      )}

      <div className="h-16" />
      <h2 className="text-[22px] font-semibold text-textPrimary">Upgrade your plan</h2>
      <p className="mt-6 text-sm font-semibold text-textSecondary">Coming soon...</p>
    </div>
  );
}
