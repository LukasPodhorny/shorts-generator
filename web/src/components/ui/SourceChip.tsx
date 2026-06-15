import { useState } from 'react';
import { CloseIcon, FileCategoryIcon, LinkIcon } from './icons';
import { fileCategory, fileChipColor, linkHost } from '@/lib/sourceFiles';

function ChipRemoveButton({ onClick }: { onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
        hovered ? 'bg-surface4 text-white' : 'text-textSecondary'
      }`}
      aria-label="Remove"
    >
      <CloseIcon size={12} />
    </button>
  );
}

// Unified attachment chip (ports SourceChip): tinted icon tile + title + type
// label + remove button.
function ChipShell({
  icon,
  accent,
  title,
  subtitle,
  maxWidth = 190,
  title_attr,
  onRemove,
}: {
  icon: React.ReactNode;
  accent: string;
  title: string;
  subtitle: string;
  maxWidth?: number;
  title_attr?: string;
  onRemove: () => void;
}) {
  return (
    <div
      title={title_attr}
      className="mr-2 flex h-14 shrink-0 items-center gap-[9px] rounded-[14px] border border-white/[0.06] bg-surface2 py-0 pl-2 pr-[6px]"
      style={{ maxWidth }}
    >
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px]"
        style={{ backgroundColor: `${accent}24`, color: accent }}
      >
        {icon}
      </div>
      <div className="flex min-w-0 flex-col justify-center">
        <span className="truncate text-[11px] font-semibold text-textPrimary">
          {title}
        </span>
        <span className="truncate text-[9px] font-medium tracking-[0.4px] text-textSecondary">
          {subtitle}
        </span>
      </div>
      <ChipRemoveButton onClick={onRemove} />
    </div>
  );
}

/** Uploaded-file chip — derives icon + accent from the file extension. */
export function FileChip({
  fileKey,
  onRemove,
}: {
  fileKey: string;
  onRemove: () => void;
}) {
  const ext = fileKey.split('.').pop() ?? '';
  const name = fileKey.split('/').pop() ?? fileKey;
  return (
    <ChipShell
      icon={<FileCategoryIcon category={fileCategory(ext)} size={17} />}
      accent={fileChipColor(ext)}
      title={name}
      subtitle={ext.toUpperCase()}
      maxWidth={130}
      onRemove={onRemove}
    />
  );
}

/** Source-link chip. */
export function LinkChip({ url, onRemove }: { url: string; onRemove: () => void }) {
  return (
    <ChipShell
      icon={<LinkIcon size={17} />}
      accent="#64B5F6"
      title={linkHost(url)}
      subtitle="LINK"
      title_attr={url}
      onRemove={onRemove}
    />
  );
}
