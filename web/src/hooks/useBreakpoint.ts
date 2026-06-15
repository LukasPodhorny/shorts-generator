import { useSyncExternalStore } from 'react';

// Responsive breakpoints mirror ResponsiveBreakpoints in the Flutter app:
//   mobile  < 600
//   tablet  600–900
//   desktop >= 900
export const BREAKPOINTS = { mobileMax: 600, desktopMin: 900 } as const;

export type ScreenCategory = 'mobile' | 'tablet' | 'desktop';

function getCategory(width: number): ScreenCategory {
  if (width < BREAKPOINTS.mobileMax) return 'mobile';
  if (width < BREAKPOINTS.desktopMin) return 'tablet';
  return 'desktop';
}

function subscribe(callback: () => void) {
  window.addEventListener('resize', callback);
  return () => window.removeEventListener('resize', callback);
}

/** Current screen category, recomputed on resize. */
export function useScreenCategory(): ScreenCategory {
  return useSyncExternalStore(
    subscribe,
    () => getCategory(window.innerWidth),
    () => 'desktop',
  );
}

/** True for the desktop layout (>= 900px). Matches DesktopHomeScreen vs HomeScreen split. */
export function useIsDesktop(): boolean {
  return useScreenCategory() === 'desktop';
}
