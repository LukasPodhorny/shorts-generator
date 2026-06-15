import type { ReactNode } from 'react';
import { useElementSize } from '@/hooks/useElementSize';

// Column count ported from ResponsiveGridDelegate: floor(width/180) clamped to
// [2,6], with tighter caps at narrower widths. Dividing the width by a fixed
// column count (rather than CSS auto-fill) makes the cards as wide as Flutter's.
function columnsFor(width: number): number {
  let n = Math.min(6, Math.max(2, Math.floor(width / 180)));
  if (width >= 1400) n = Math.min(n, 6);
  else if (width >= 1100) n = Math.min(n, 5);
  else if (width >= 900) n = Math.min(n, 4);
  return n;
}

// Responsive media grid (minItemWidth 180, aspect 0.6) shared by the videos
// list and the series detail view.
export function MediaGrid({ children }: { children: ReactNode }) {
  const { ref, width } = useElementSize<HTMLDivElement>();
  const columns = width > 0 ? columnsFor(width) : 2;
  return (
    <div
      ref={ref}
      className="grid gap-3 px-4"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {children}
    </div>
  );
}
