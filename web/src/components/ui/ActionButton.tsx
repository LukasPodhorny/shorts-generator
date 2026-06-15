import { useState, type ReactNode } from 'react';
import { Spinner } from './Spinner';

// Port of ActionPillButton: full-width, 54px, radius 16, optional icon, loading
// spinner and disabled dimming.
export function ActionButton({
  text,
  backgroundColor,
  textColor,
  borderColor,
  hoverBackground,
  icon,
  onClick,
  fontWeight = 500,
  isLoading = false,
  disabled = false,
}: {
  text: string;
  backgroundColor: string;
  textColor: string;
  borderColor?: string;
  /** Background shown on hover (e.g. surface1 for the quiet "Log in" button). */
  hoverBackground?: string;
  icon?: ReactNode;
  onClick?: () => void;
  fontWeight?: number;
  isLoading?: boolean;
  disabled?: boolean;
}) {
  const [hovered, setHovered] = useState(false);
  const isDisabled = disabled || isLoading;
  const bg = hovered && hoverBackground && !isDisabled ? hoverBackground : backgroundColor;
  return (
    <button
      type="button"
      onClick={isDisabled ? undefined : onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      disabled={isDisabled}
      className="flex h-[54px] w-full items-center justify-center rounded-2xl transition-colors"
      style={{
        backgroundColor: bg,
        color: textColor,
        border: borderColor ? `1px solid ${borderColor}` : undefined,
        cursor: isDisabled ? 'default' : 'pointer',
        opacity: disabled && !isLoading ? 0.4 : 1,
      }}
    >
      {isLoading ? (
        <Spinner size={20} strokeWidth={2} style={{ color: textColor }} />
      ) : (
        <span className="flex items-center gap-3">
          {icon}
          <span className="text-base tracking-[0.1px]" style={{ fontWeight }}>
            {text}
          </span>
        </span>
      )}
    </button>
  );
}
