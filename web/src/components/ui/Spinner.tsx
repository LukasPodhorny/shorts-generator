// Port of AppLoadingIndicator (constants.dart): a simple circular spinner.
import type { CSSProperties } from 'react';

export function Spinner({
  size = 24,
  strokeWidth = 3,
  className = '',
  style,
}: {
  size?: number;
  strokeWidth?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-current border-t-transparent text-textPrimary ${className}`}
      style={{ width: size, height: size, borderWidth: strokeWidth, ...style }}
      role="status"
      aria-label="Loading"
    />
  );
}
