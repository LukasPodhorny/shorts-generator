import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth/AuthProvider';
import { useOAuthGrants, useUserProfile } from '@/hooks/queries';
import { revokeOAuthGrant } from '@/api/oauth';
import { apiErrorMessage } from '@/lib/apiClient';
import { API_BASE_URL } from '@/lib/config';
import { queryKeys } from '@/lib/queryClient';
import { toast } from '@/store/toastStore';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { PersonIcon } from '@/components/ui/icons';
import { Spinner } from '@/components/ui/Spinner';
import { Avatar } from '@/components/ui/Avatar';

// Port of desktop_account_screen: profile header (avatar, credits, tier, email)
// and an "Upgrade your plan — Coming soon" section.
export default function AccountScreen() {
  const { user } = useAuth();
  const { data: profile, isLoading, isError } = useUserProfile();
  const { data: grants } = useOAuthGrants();
  const queryClient = useQueryClient();
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const revoke = async (grantId: number) => {
    setRevokingId(grantId);
    try {
      await revokeOAuthGrant(grantId);
      await queryClient.invalidateQueries({ queryKey: queryKeys.oauthGrants });
    } catch (e) {
      toast(apiErrorMessage(e));
    } finally {
      setRevokingId(null);
    }
  };

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

      <div className="h-16" />
      <h2 className="text-[22px] font-semibold text-textPrimary">Connected apps</h2>
      <p className="mt-3 max-w-xl text-sm leading-relaxed text-textSecondary">
        AI assistants you connected with one-click login. Revoking removes their
        access immediately.
      </p>
      <div className="mt-6 flex max-w-xl flex-col gap-3">
        {grants === undefined ? (
          <Spinner size={24} />
        ) : grants.length === 0 ? (
          <p className="text-sm text-textSecondary">No connected apps yet.</p>
        ) : (
          grants.map((grant) => (
            <div
              key={grant.id}
              className="flex items-center justify-between gap-4 rounded-2xl border border-surface3/40 bg-surface1 px-5 py-4"
            >
              <div className="flex min-w-0 flex-col">
                <span className="truncate text-[15px] font-semibold text-textPrimary">
                  {grant.clientName ?? 'AI assistant'}
                </span>
                <span className="mt-0.5 text-xs text-textSecondary">
                  {grant.scopes.join(', ')} · connected{' '}
                  {new Date(grant.createdAt).toLocaleDateString()}
                </span>
              </div>
              <button
                type="button"
                disabled={revokingId === grant.id}
                onClick={() => revoke(grant.id)}
                className="shrink-0 rounded-full border border-surface3 px-4 py-2 text-sm font-medium text-textPrimary hover:bg-surface2 disabled:opacity-40"
              >
                {revokingId === grant.id ? 'Revoking...' : 'Revoke'}
              </button>
            </div>
          ))
        )}
      </div>

      <div className="h-16" />
      <h2 className="text-[22px] font-semibold text-textPrimary">Connect an AI assistant</h2>
      <div className="mt-3 max-w-xl text-sm leading-relaxed text-textSecondary">
        <p>
          In Claude, ChatGPT, or your coding tool, add a custom MCP server with
          this URL, then log in with your pdftoreel account when asked:
        </p>
        <p className="mt-3 select-all rounded-xl bg-surface1 px-4 py-3 font-mono text-[13px] text-textPrimary">
          {API_BASE_URL ? `${API_BASE_URL}/mcp` : 'https://api.pdftoreel.com/mcp'}
        </p>
      </div>
    </div>
  );
}
