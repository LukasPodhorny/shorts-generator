import { useState } from 'react';
import { useIsDesktop } from '@/hooks/useBreakpoint';
import { DesktopSidebar, type SidebarTab } from '@/components/layout/DesktopSidebar';
import GenerateScreen from '@/screens/generate/GenerateScreen';

// DEV-ONLY preview: shows the desktop sidebar + GENERATE screen so the layout
// can be compared against the Flutter app before the real shell (Step 4).
export default function PreviewGenerate() {
  const isDesktop = useIsDesktop();
  const [tab, setTab] = useState<SidebarTab>('generate');

  if (!isDesktop) return <GenerateScreen />;

  return (
    <div className="flex h-full w-full bg-background">
      <DesktopSidebar activeTab={tab} onNavigate={setTab} />
      <div className="min-w-0 flex-1">
        <GenerateScreen />
      </div>
    </div>
  );
}
