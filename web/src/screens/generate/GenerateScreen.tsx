import { useIsDesktop } from '@/hooks/useBreakpoint';
import { DesktopGenerate } from './DesktopGenerate';
import { MobileGenerate } from './MobileGenerate';

// Single adaptive GENERATE screen. Desktop (>=900px) renders the 2-pane
// carousel/config layout; narrow widths reproduce the Flutter mobile generate
// UI (avatar strip, slider, carousel, bottom prompt bar).
export default function GenerateScreen() {
  return useIsDesktop() ? <DesktopGenerate /> : <MobileGenerate />;
}
