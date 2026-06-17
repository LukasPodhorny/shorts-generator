import type { CSSProperties } from 'react';

// A shimmering placeholder block. Defaults to filling its parent; pass a
// className (e.g. rounded-full) or style to shape it to match the real content.
export function Skeleton({
  className = '',
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return <div className={`skeleton ${className}`} style={style} />;
}
