import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useIsDesktop } from '@/hooks/useBreakpoint';
import { DesktopSidebar, type SidebarTab } from '@/components/layout/DesktopSidebar';
import { MobileTopBar } from '@/components/layout/MobileTopBar';
import { ProfileDrawer } from '@/components/layout/ProfileDrawer';
import { LogoutDialog } from '@/components/layout/LogoutDialog';
import { useLogout } from '@/components/layout/useLogout';

function tabForPath(pathname: string): SidebarTab {
  if (pathname.startsWith('/videos')) return 'videos';
  if (pathname.startsWith('/account')) return 'account';
  return 'generate';
}

// The authenticated shell: desktop sidebar + content, or mobile top bar +
// content with a profile drawer. Replaces ResponsiveLayout's mobile/desktop split.
export function AppShell() {
  const isDesktop = useIsDesktop();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const logout = useLogout();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [logoutOpen, setLogoutOpen] = useState(false);

  if (isDesktop) {
    return (
      <div className="flex h-full w-full bg-background">
        <DesktopSidebar
          activeTab={tabForPath(pathname)}
          onNavigate={(tab) => navigate(tab === 'generate' ? '/' : `/${tab}`)}
          onLogout={() => setLogoutOpen(true)}
        />
        <div className="min-w-0 flex-1">
          <Outlet />
        </div>
        <LogoutDialog
          open={logoutOpen}
          onClose={() => setLogoutOpen(false)}
          onConfirm={() => void logout()}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col bg-background">
      <MobileTopBar onOpenDrawer={() => setDrawerOpen(true)} />
      <div className="min-h-0 flex-1">
        <Outlet />
      </div>
      <ProfileDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onLogout={() => void logout()}
      />
    </div>
  );
}
