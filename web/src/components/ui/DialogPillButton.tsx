import { useState, type CSSProperties } from 'react';

// Pill-shaped dialog action button with an instant (no-fade) hover state.
// Ports DialogPillButton from source_input_shared.dart.
export function DialogPillButton({
  label,
  background,
  hoverBackground,
  textColor,
  onClick,
}: {
  label: string;
  background?: string;
  hoverBackground: string;
  textColor: string;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const style: CSSProperties = {
    backgroundColor: hovered ? hoverBackground : (background ?? 'transparent'),
    color: textColor,
  };
  return (
    <button
      type="button"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={onClick}
      style={style}
      className="cursor-pointer rounded-full px-[22px] py-3 text-sm font-semibold"
    >
      {label}
    </button>
  );
}
