import { useState } from 'react';
import { useAvatars } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import { toast } from '@/store/toastStore';
import { avatarDisplayName } from '@/types/models';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorIcon } from '@/components/ui/icons';
import { AvatarCircle } from './AvatarCircle';

// Ports AvatarSelectionGrid: searchable 4-column grid inside the desktop
// configuration panel. Reads avatars + selection from query/store.
export function AvatarSelectionGrid() {
  const [query, setQuery] = useState('');
  const { data: avatars, isLoading, isError } = useAvatars();
  const selected = useUiStore((s) => s.selectedAvatarNames);
  const toggleAvatar = useUiStore((s) => s.toggleAvatar);

  const q = query.toLowerCase();
  const filtered = (avatars ?? []).filter(
    (a) => !q || avatarDisplayName(a).toLowerCase().includes(q),
  );

  return (
    <div className="flex h-full flex-col rounded-[30px] bg-surface2 p-3">
      <div className="h-10 px-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="search for avatars..."
          className="h-full w-full bg-transparent text-sm text-textPrimary caret-textPrimary outline-none placeholder:text-textSecondary"
        />
      </div>
      <div className="h-1" />
      {/* p-1.5 gives the 1.05× selected scale + checkmark badge room so they
          aren't clipped by the scroll container edges. */}
      <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
        {isLoading && (
          <div className="grid grid-cols-4 gap-1.5">
            {Array.from({ length: 16 }).map((_, i) => (
              <Skeleton key={i} className="aspect-square w-full rounded-full" />
            ))}
          </div>
        )}
        {isError && (
          <div className="flex h-full items-center justify-center text-error">
            <ErrorIcon size={28} />
          </div>
        )}
        {!isLoading && !isError && (
          <div className="grid grid-cols-4 gap-1.5">
            {filtered.map((avatar) => (
              <AvatarCircle
                key={avatar.name}
                avatar={avatar}
                title={avatarDisplayName(avatar)}
                selected={selected.has(avatar.name)}
                fill
                checkSize={10}
                onClick={() => {
                  if (!toggleAvatar(avatar.name)) {
                    toast('You can select up to 4 avatars');
                  }
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
