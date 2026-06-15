import type { VideoTemplate } from '@/types/models';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { CarouselVideoPlayer } from './CarouselVideoPlayer';
import { TemplateTagPills } from './TemplateTagPills';

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
      />

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
