import { useId, useState } from 'react';
import type { VideoTemplate } from '@/types/models';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { CarouselVideoPlayer } from './CarouselVideoPlayer';
import { TemplateTagPills } from './TemplateTagPills';

function TemplateInfo({ description }: { description: string }) {
  const descriptionId = useId();
  const [open, setOpen] = useState(false);
  return (
    <div
      onPointerEnter={(event) => { if (event.pointerType === 'mouse') setOpen(true); }}
      onPointerLeave={(event) => { if (event.pointerType === 'mouse') setOpen(false); }}
    >
      <button
        type="button"
        aria-label="About this template"
        aria-expanded={open}
        aria-controls={descriptionId}
        aria-describedby={descriptionId}
        className="grid size-8 place-items-center rounded-full text-white/80 hover:bg-white/15 focus-visible:outline-2 focus-visible:outline-white"
        onClick={(event) => {
          const mouse = 'pointerType' in event.nativeEvent && event.nativeEvent.pointerType === 'mouse';
          setOpen((visible) => mouse || !visible);
        }}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }}
      >
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v6m0-10v1" />
        </svg>
      </button>
      <div id={descriptionId} hidden={!open} className="absolute inset-x-0 bottom-full z-10 pb-2">
        <p className="rounded-xl border border-white/15 bg-neutral-950 p-3 text-sm leading-snug text-white shadow-lg">
          {description}
        </p>
      </div>
    </div>
  );
}

// The 9:16 template card shared by the desktop and mobile carousels: preview
// video, toggleable tag pills (top-left), credit cost (top-right), and a
// background-colored fade overlay for off-center cards.
export function TemplateCard({
  template,
  isSelected,
  fadeOpacity,
  tagScale = 1,
  radius = 30,
}: {
  template: VideoTemplate;
  isSelected: boolean;
  fadeOpacity: number;
  tagScale?: number;
  radius?: number;
}) {
  return (
    <div
      className="relative h-full w-full overflow-hidden bg-neutral-900"
      style={{ borderRadius: radius }}
    >
      <CarouselVideoPlayer
        videoUrl={template.previewUrl}
        thumbnailUrl={template.thumbnailUrl ?? ''}
        isSelected={isSelected}
        fit={(template.width ?? 1080) > (template.height ?? 1920) ? 'contain' : 'cover'}
      />

      <div className="absolute inset-x-0 bottom-0 bg-linear-to-t from-black/90 to-transparent px-5 pb-6 pt-12 text-white">
        <p className="text-xs font-medium opacity-75">{(template.width ?? 1080) > (template.height ?? 1920) ? '16:9 · Landscape' : '9:16 · Portrait'}</p>
        <div className="relative mt-1 flex items-center gap-2">
          <p className="text-lg font-semibold capitalize">{template.name.replaceAll('_', ' ')}</p>
          {isSelected && template.description && (
            <TemplateInfo description={template.description} />
          )}
        </div>
      </div>

      {isSelected && (
        <div className="absolute left-[11px] right-[60px] top-[11px]">
          <TemplateTagPills template={template} scale={tagScale} />
        </div>
      )}

      <div className="absolute right-[9px] top-[11px] flex items-center gap-[5px] drop-shadow-[1px_1px_10px_rgba(0,0,0,0.6)]">
        <span className="text-base font-semibold text-white">{template.credits}</span>
        <CreditIcon size={12} color="#ffffff" />
      </div>

      {fadeOpacity > 0 && (
        <div
          className="pointer-events-none absolute inset-0"
          style={{ backgroundColor: 'var(--color-background)', opacity: fadeOpacity }}
        />
      )}
    </div>
  );
}
