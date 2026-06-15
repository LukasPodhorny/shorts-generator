import type { CSSProperties } from 'react';

// Renders a monochrome SVG from /public/icons recolored to `color` via CSS
// mask — the web equivalent of Flutter's ColorFilter.mode(..., srcIn) on
// SvgPicture.asset. `color` defaults to currentColor so it can inherit text color.
export function MaskIcon({
  src,
  size = 24,
  color = 'currentColor',
  className = '',
  style,
}: {
  src: string;
  size?: number;
  color?: string;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={className}
      aria-hidden
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        backgroundColor: color,
        WebkitMaskImage: `url(${src})`,
        maskImage: `url(${src})`,
        WebkitMaskRepeat: 'no-repeat',
        maskRepeat: 'no-repeat',
        WebkitMaskPosition: 'center',
        maskPosition: 'center',
        WebkitMaskSize: 'contain',
        maskSize: 'contain',
        ...style,
      }}
    />
  );
}

/** The credit "coin" icon, recolored. Used throughout cost displays. */
export function CreditIcon({
  size = 12,
  color = 'currentColor',
  className = '',
}: {
  size?: number;
  color?: string;
  className?: string;
}) {
  return <MaskIcon src="/icons/credit.svg" size={size} color={color} className={className} />;
}
