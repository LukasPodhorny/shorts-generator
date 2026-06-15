import { useState } from 'react';
import { useAvatars } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import { toast } from '@/store/toastStore';
import { Spinner } from '@/components/ui/Spinner';
import { ErrorIcon, SearchIcon } from '@/components/ui/icons';
import { AvatarCircle } from './AvatarCircle';
import { AvatarSearchSheet } from './AvatarSearchSheet';

// Ports the mobile ProfileSelector: a horizontally-scrolling avatar strip with
// a leading search button and edge fade, inside a rounded surface.
export function ProfileSelector() {
  const { data: avatars, isLoading, isError } = useAvatars();
  const selected = useUiStore((s) => s.selectedAvatarNames);
  const toggleAvatar = useUiStore((s) => s.toggleAvatar);
  const [sheetOpen, setSheetOpen] = useState(false);

  return (
    <div className="mx-[18px] h-[84px] overflow-hidden rounded-[30px] border border-surface2 bg-surface1">
      {isLoading && (
        <div className="flex h-full items-center justify-center">
          <Spinner />
        </div>
      )}
      {isError && (
        <div className="flex h-full items-center justify-center text-error">
          <ErrorIcon />
        </div>
      )}
      {!isLoading && !isError && (
        <div
          className="flex h-full items-center gap-[5px] overflow-x-auto px-[15px]"
          style={{
            maskImage:
              'linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%)',
            WebkitMaskImage:
              'linear-gradient(to right, transparent 0%, black 5%, black 95%, transparent 100%)',
          }}
        >
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className="flex h-[62px] w-[62px] shrink-0 items-center justify-center rounded-full border border-surface3 bg-surface2 text-textSecondary"
          >
            <SearchIcon size={26} />
          </button>
          {(avatars ?? []).map((avatar) => (
            <AvatarCircle
              key={avatar.name}
              avatar={avatar}
              selected={selected.has(avatar.name)}
              size={62}
              badgePadding={5}
              checkSize={10}
              onClick={() => {
                if (!toggleAvatar(avatar.name)) toast('You can select up to 4 avatars');
              }}
            />
          ))}
        </div>
      )}

      {sheetOpen && (
        <AvatarSearchSheet avatars={avatars ?? []} onClose={() => setSheetOpen(false)} />
      )}
    </div>
  );
}
