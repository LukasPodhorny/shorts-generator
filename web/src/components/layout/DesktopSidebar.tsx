import { useState, type ReactNode } from 'react';
import { MaskIcon, CreditIcon } from '@/components/ui/MaskIcon';
import { Avatar } from '@/components/ui/Avatar';
import { useUserProfile } from '@/hooks/queries';
import { useAuth } from '@/auth/AuthProvider';

export type SidebarTab = 'generate' | 'videos' | 'account';

function NavItem({
  icon,
  iconNode,
  label,
  selected,
  onClick,
}: {
  icon?: string;
  /** Custom leading element (e.g. the user's avatar) replacing the svg icon. */
  iconNode?: ReactNode;
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const bg = selected
    ? 'var(--color-background)'
    : hovered
      ? 'var(--color-surface2)'
      : 'transparent';
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="mx-3 my-0.5 flex items-center gap-3 rounded-[15px] px-3 py-3 text-left"
      style={{ backgroundColor: bg }}
    >
      {iconNode ?? (
        <MaskIcon src={icon!} size={22} color="var(--color-textPrimary)" />
      )}
      <span className="text-sm font-medium text-textPrimary">{label}</span>
    </button>
  );
}

// Ports the Flutter DesktopSidebar: logo + credits header, Generate/Videos nav,
// and Account/Log out pinned to the bottom. Width scales with the viewport
// (clamp 260–340, ~14vw).
export function DesktopSidebar({
  activeTab,
  onNavigate,
  onLogout,
}: {
  activeTab: SidebarTab;
  onNavigate: (tab: SidebarTab) => void;
  onLogout?: () => void;
}) {
  const { data: profile } = useUserProfile();
  const { user } = useAuth();

  return (
    <div
      className="flex h-full shrink-0 flex-col bg-surface1"
      style={{ width: 'clamp(260px, 14vw, 340px)' }}
    >
      {/* Logo + credits header */}
      <div className="flex items-center gap-3 px-5 py-5">
        <MaskIcon src="/icons/logo.svg" size={30} color="var(--color-neon)" />
        <span className="flex-1 truncate text-sm font-semibold text-textPrimary">
          PDF to Reel
        </span>
        {profile && (
          <span className="flex items-center gap-[5px] text-sm font-semibold text-textPrimary">
            {profile.credits}
            <CreditIcon size={10} color="var(--color-textPrimary)" />
          </span>
        )}
      </div>

      <div className="h-4" />

      <NavItem
        icon="/icons/generate_icon.svg"
        label="Generate"
        selected={activeTab === 'generate'}
        onClick={() => onNavigate('generate')}
      />
      <NavItem
        icon="/icons/video_icon.svg"
        label="Videos"
        selected={activeTab === 'videos'}
        onClick={() => onNavigate('videos')}
      />

      <div className="flex-1" />

      <NavItem
        icon="/icons/account_icon.svg"
        iconNode={
          user?.photoURL ? (
            <Avatar
              src={user.photoURL}
              className="h-[22px] w-[22px] rounded-full object-cover"
              fallback={
                <MaskIcon
                  src="/icons/account_icon.svg"
                  size={22}
                  color="var(--color-textPrimary)"
                />
              }
            />
          ) : undefined
        }
        label="Account"
        selected={activeTab === 'account'}
        onClick={() => onNavigate('account')}
      />
      <NavItem
        icon="/icons/logout_icon.svg"
        label="Log out"
        selected={false}
        onClick={() => onLogout?.()}
      />
      <div className="h-6" />
    </div>
  );
}
