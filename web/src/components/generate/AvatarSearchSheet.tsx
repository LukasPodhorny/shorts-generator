import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useUiStore } from '@/store/uiStore';
import { toast } from '@/store/toastStore';
import { avatarDisplayName, type Avatar } from '@/types/models';
import { SearchIcon, CloseIcon } from '@/components/ui/icons';
import { AvatarCircle } from './AvatarCircle';

// Ports _AvatarSearchSheet: a bottom sheet (70vh) with a search field and a
// 4-column avatar grid, opened from the mobile ProfileSelector's search button.
export function AvatarSearchSheet({
  avatars,
  onClose,
}: {
  avatars: Avatar[];
  onClose: () => void;
}) {
  const [query, setQuery] = useState('');
  const selected = useUiStore((s) => s.selectedAvatarNames);
  const toggleAvatar = useUiStore((s) => s.toggleAvatar);

  const q = query.toLowerCase();
  const filtered = q
    ? avatars.filter((a) => avatarDisplayName(a).toLowerCase().includes(q))
    : avatars;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col justify-end bg-black/50"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex h-[70vh] flex-col rounded-t-[20px] bg-surface1">
        <div className="mx-auto mb-2 mt-2.5 h-1 w-10 rounded-sm bg-surface3" />
        <div className="mx-4 my-2 flex h-11 items-center gap-2 rounded-xl border border-surface3 bg-surface2 px-3">
          <SearchIcon size={20} className="text-textSecondary" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="search for avatars..."
            className="h-full flex-1 bg-transparent text-sm text-textPrimary outline-none placeholder:text-textSecondary"
          />
          {query && (
            <button type="button" onClick={() => setQuery('')} className="text-textSecondary">
              <CloseIcon size={18} />
            </button>
          )}
        </div>
        {/* Generous padding so the 1.05× selected scale + checkmark badge of
            edge/corner avatars aren't clipped by the scroll container. */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="grid grid-cols-4 gap-2.5">
            {filtered.map((avatar) => (
              <AvatarCircle
                key={avatar.name}
                avatar={avatar}
                title={avatarDisplayName(avatar)}
                selected={selected.has(avatar.name)}
                fill
                checkSize={12}
                badgePadding={5}
                onClick={() => {
                  if (!toggleAvatar(avatar.name)) toast('You can select up to 4 avatars');
                }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
