import { useState } from 'react';
import { useAvatars } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import { avatarFaceUrl, avatarStaticFaceUrl, type Avatar } from '@/types/models';
import { PersonIcon } from '@/components/ui/icons';
import { AutoChip } from './AutoChip';

const SIZE = 34;
const OVERLAP = 16; // px the circles tuck under each other (tightly coupled)

function FaceCircle({
  avatar,
  index,
  hovered,
}: {
  avatar: Avatar | null;
  index: number;
  hovered: boolean;
}) {
  const url = avatar ? avatarStaticFaceUrl(avatar) ?? avatarFaceUrl(avatar) : null;
  // A border in the card color carves each circle out of the one behind it.
  return (
    <span
      className="flex items-center justify-center overflow-hidden rounded-full bg-surface3 bg-cover bg-center text-textSecondary"
      style={{
        width: SIZE,
        height: SIZE,
        marginLeft: index === 0 ? 0 : -(OVERLAP - (hovered ? 4 : 0)),
        border: '2px solid var(--color-surface1)',
        backgroundImage: url ? `url('${url}')` : undefined,
        transition: 'margin-left 200ms cubic-bezier(0.34, 1.4, 0.64, 1)',
      }}
    >
      {!url && <PersonIcon size={17} />}
    </span>
  );
}

// Minimal avatar control: a tight cluster of overlapping avatar faces that
// spread apart slightly on hover. Shows the chosen cast (with a +N overflow);
// when none are picked it previews real catalog avatars with an "auto" hint so
// it's clear the AI will choose.
export function AvatarStackButton({ onClick }: { onClick: () => void }) {
  const { data: avatars } = useAvatars();
  const selectedNames = useUiStore((s) => s.selectedAvatarNames);
  const [hovered, setHovered] = useState(false);

  const all = avatars ?? [];
  const selected = all.filter((a) => selectedNames.has(a.name));
  // When nothing is picked yet, preview real avatars from the catalog (not
  // blank silhouettes) so the control reads as "choose your cast".
  const examples = all.slice(0, 3);
  const shown =
    selected.length > 0
      ? selected.slice(0, 3)
      : examples.length > 0
        ? examples
        : [null, null, null];
  const overflow = selected.length - 3;

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={selected.length > 0 ? `${selected.length} avatar(s) selected` : 'Choose avatars'}
      aria-label="Choose avatars"
      className="relative flex h-12 items-center justify-center px-1"
    >
      <span className="flex items-center">
        {shown.map((a, i) => (
          <FaceCircle key={a?.name ?? `ph-${i}`} avatar={a} index={i} hovered={hovered} />
        ))}
        {overflow > 0 && (
          <span
            className="flex items-center justify-center rounded-full bg-surface3 text-[10px] font-bold text-textPrimary"
            style={{
              width: SIZE,
              height: SIZE,
              marginLeft: -(OVERLAP - (hovered ? 4 : 0)),
              border: '2px solid var(--color-surface1)',
            }}
          >
            +{overflow}
          </span>
        )}
      </span>
      {selected.length === 0 && <AutoChip />}
    </button>
  );
}
