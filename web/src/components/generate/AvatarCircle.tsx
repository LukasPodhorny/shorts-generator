import { useState } from 'react';
import { avatarFaceUrl, avatarStaticFaceUrl, type Avatar } from '@/types/models';

// Matches Flutter's AnimatedScale(curve: easeOutBack) — a subtle grow with a
// slight overshoot, no wobble.
const SELECTED_SCALE = 1.08;
const EASE_OUT_BACK = 'cubic-bezier(0.34, 1.56, 0.64, 1)';

// One circular avatar with the minecraft_bg backdrop, a white selection ring,
// hover wash and a neon checkmark badge — shared by the desktop grid, mobile
// strip and search sheet. The ring is an absolutely-positioned overlay (not a
// border) so toggling selection never changes the box size, avoiding wobble.
export function AvatarCircle({
  avatar,
  selected,
  onClick,
  size,
  fill = false,
  ringWidth = 2.5,
  badgePadding = 3,
  checkSize = 8,
  title,
}: {
  avatar: Avatar;
  selected: boolean;
  onClick: () => void;
  /** Fixed pixel size; ignored when `fill` is set. */
  size?: number;
  /** Fill the parent cell as a square (used in CSS grids). */
  fill?: boolean;
  ringWidth?: number;
  badgePadding?: number;
  checkSize?: number;
  title?: string;
}) {
  const [hovered, setHovered] = useState(false);
  const [imgError, setImgError] = useState(false);
  const faceUrl = avatarStaticFaceUrl(avatar) ?? avatarFaceUrl(avatar) ?? '';

  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`relative shrink-0 cursor-pointer ${fill ? 'aspect-square w-full' : ''}`}
      style={{
        width: fill ? undefined : size,
        height: fill ? undefined : size,
        transform: selected ? `scale(${SELECTED_SCALE})` : 'scale(1)',
        transition: `transform 200ms ${EASE_OUT_BACK}`,
      }}
    >
      <div
        className="relative h-full w-full overflow-hidden rounded-full bg-cover bg-center"
        style={{ backgroundImage: "url('/images/minecraft_bg.jpg')" }}
      >
        {faceUrl && !imgError && (
          <img
            src={faceUrl}
            alt=""
            onError={() => setImgError(true)}
            className="h-full w-full object-cover"
          />
        )}
        {hovered && <div className="absolute inset-0 bg-white/15" />}
      </div>

      {/* Selection ring: overlay box-shadow so it never shifts the layout. */}
      {selected && (
        <div
          className="pointer-events-none absolute inset-0 rounded-full"
          style={{ boxShadow: `inset 0 0 0 ${ringWidth}px #fff` }}
        />
      )}

      {selected && (
        <span
          className="absolute bottom-0 right-0 flex items-center justify-center rounded-full bg-neon"
          style={{ padding: badgePadding }}
        >
          {/* Inline SVG (rather than a CSS mask) so the badge renders instantly
              on first selection — no network fetch that briefly shows an
              unmasked block before the checkmark shape loads. */}
          <svg
            width={checkSize}
            height={checkSize}
            viewBox="0 0 69 58"
            fill="none"
            aria-hidden
          >
            <path
              d="M60 8.50021L25.625 49.5002L8.5 29.0002"
              stroke="var(--color-surface1)"
              strokeWidth={17}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      )}
    </button>
  );
}
