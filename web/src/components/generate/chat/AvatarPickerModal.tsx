import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { DialogPillButton } from '@/components/ui/DialogPillButton';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorIcon } from '@/components/ui/icons';
import { useAvatars } from '@/hooks/queries';
import { useUiStore, MAX_SELECTED_AVATARS } from '@/store/uiStore';
import { toast } from '@/store/toastStore';
import {
  avatarDisplayName,
  avatarFaceUrl,
  avatarStaticFaceUrl,
  type Avatar,
} from '@/types/models';

// One round avatar with an animated white selection ring and a neon check badge
// sitting on the circle's edge (sized for this picker; tuned smaller/more dense
// than the studio grid so the modal doesn't blow the faces up).
function AvatarTile({
  avatar,
  selected,
  onToggle,
}: {
  avatar: Avatar;
  selected: boolean;
  onToggle: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const [imgError, setImgError] = useState(false);
  const faceUrl = avatarStaticFaceUrl(avatar) ?? avatarFaceUrl(avatar) ?? '';

  const ring = selected
    ? 'inset 0 0 0 2.5px #fff'
    : hovered
      ? 'inset 0 0 0 2px rgba(255,255,255,0.35)'
      : 'inset 0 0 0 0 rgba(255,255,255,0)';

  return (
    <button
      type="button"
      title={avatarDisplayName(avatar)}
      onClick={onToggle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="relative aspect-square w-full"
    >
      <div
        className="h-full w-full overflow-hidden rounded-full bg-cover bg-center"
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
      </div>

      <div
        className="pointer-events-none absolute inset-0 rounded-full"
        style={{ boxShadow: ring, transition: 'box-shadow 150ms ease' }}
      />

      {selected && (
        <span
          className="absolute bottom-[6%] right-[6%] flex items-center justify-center rounded-full bg-neon"
          style={{ padding: 4 }}
        >
          <svg width={14} height={14} viewBox="0 0 69 58" fill="none" aria-hidden>
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

// Avatar picker for the chat composer. Choosing avatars is optional: an empty
// selection lets the backend parser pick a fitting cast.
export function AvatarPickerModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data: avatars, isLoading, isError } = useAvatars();
  const selected = useUiStore((s) => s.selectedAvatarNames);
  const toggleAvatar = useUiStore((s) => s.toggleAvatar);
  const count = useUiStore((s) => s.selectedAvatarNames.size);
  const [query, setQuery] = useState('');

  const q = query.toLowerCase();
  const filtered = (avatars ?? []).filter(
    (a) => !q || avatarDisplayName(a).toLowerCase().includes(q),
  );

  return (
    <Modal open={open} onClose={onClose} width={580}>
      <div className="flex flex-col" style={{ height: 'min(72vh, 600px)' }}>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold text-textPrimary">Avatars</h2>
          <span className="text-xs text-textSecondary">
            {count > 0
              ? `${count}/${MAX_SELECTED_AVATARS} selected`
              : 'Optional - AI picks if empty'}
          </span>
        </div>

        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search avatars..."
          className="mt-4 h-10 w-full rounded-full bg-surface2 px-4 text-sm text-textPrimary caret-textPrimary outline-none placeholder:text-textSecondary"
        />

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto p-1">
          {isLoading && (
            <div className="grid grid-cols-5 gap-3.5">
              {Array.from({ length: 20 }).map((_, i) => (
                <Skeleton key={i} className="aspect-square w-full rounded-full" />
              ))}
            </div>
          )}
          {isError && (
            <div className="flex h-40 items-center justify-center text-error">
              <ErrorIcon size={28} />
            </div>
          )}
          {!isLoading && !isError && (
            <div className="grid grid-cols-5 gap-3.5">
              {filtered.map((avatar) => (
                <AvatarTile
                  key={avatar.name}
                  avatar={avatar}
                  selected={selected.has(avatar.name)}
                  onToggle={() => {
                    if (!toggleAvatar(avatar.name)) {
                      toast(`You can select up to ${MAX_SELECTED_AVATARS} avatars`);
                    }
                  }}
                />
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end">
          <DialogPillButton
            label="Done"
            hoverBackground="var(--color-surface2)"
            textColor="var(--color-textPrimary)"
            onClick={onClose}
          />
        </div>
      </div>
    </Modal>
  );
}
