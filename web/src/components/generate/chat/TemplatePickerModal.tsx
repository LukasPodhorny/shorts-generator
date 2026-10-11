import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { DialogPillButton } from '@/components/ui/DialogPillButton';
import { Skeleton } from '@/components/ui/Skeleton';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { ErrorIcon, AutoAwesomeIcon } from '@/components/ui/icons';
import { CarouselVideoPlayer } from '@/components/generate/CarouselVideoPlayer';
import { TemplateTagPills } from '@/components/generate/TemplateTagPills';
import { useTemplates } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import type { VideoTemplate } from '@/types/models';

export function prettyTemplateName(name: string): string {
  const cleaned = name.replace(/[-_]+/g, ' ').trim();
  return cleaned.replace(/\b\w/g, (c) => c.toUpperCase());
}

// Always-present ring overlay that animates its width/brightness between
// rest -> hover -> selected (box-shadow transition, like the composer border).
// White when selected, a dimmer/thinner white on hover.
function SelectRing({ selected, hovered }: { selected: boolean; hovered: boolean }) {
  const shadow = selected
    ? 'inset 0 0 0 0.8px rgba(255,255,255,0.8)'
    : hovered
      ? 'inset 0 0 0 0.8px rgba(255,255,255,0.3)'
      : 'inset 0 0 0 0 rgba(255,255,255,0)';
  return (
    <div
      className="pointer-events-none absolute inset-0 rounded-2xl"
      style={{ boxShadow: shadow, transition: 'box-shadow 150ms ease' }}
    />
  );
}

// Neon check badge, matching the avatar selection grid (AvatarCircle).
function CheckBadge() {
  return (
    <span
      className="absolute left-2 top-2 flex items-center justify-center rounded-full bg-neon"
      style={{ padding: 5 }}
    >
      <svg width={12} height={12} viewBox="0 0 69 58" fill="none" aria-hidden>
        <path
          d="M60 8.50021L25.625 49.5002L8.5 29.0002"
          stroke="var(--color-surface1)"
          strokeWidth={17}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function TemplateCard({
  template,
  selected,
  onClick,
}: {
  template: VideoTemplate;
  selected: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="relative aspect-9/16 overflow-hidden rounded-2xl bg-neutral-900 text-left"
    >
      {/* Plays the preview while hovered; otherwise shows the thumbnail. */}
      <CarouselVideoPlayer
        videoUrl={template.previewUrl}
        thumbnailUrl={template.thumbnailUrl ?? ''}
        isSelected={hovered}
      />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-linear-to-t from-black/70 to-transparent p-2.5 pt-8">
        <span className="line-clamp-1 text-[13px] font-semibold text-white">
          {prettyTemplateName(template.name)}
        </span>
      </div>
      <div className="absolute right-2 top-2 flex items-center gap-1 drop-shadow-[0_1px_4px_rgba(0,0,0,0.7)]">
        <span className="text-xs font-bold text-white">{template.credits}</span>
        <CreditIcon size={10} color="#ffffff" />
      </div>
      <SelectRing selected={selected} hovered={hovered} />
      {selected && <CheckBadge />}
    </button>
  );
}

function AiChooseCard({ selected, onClick }: { selected: boolean; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="relative flex aspect-9/16 flex-col items-center justify-center gap-3 overflow-hidden rounded-2xl bg-surface2"
    >
      <span
        className="flex h-12 w-12 items-center justify-center rounded-full bg-surface3"
        style={{ color: 'var(--color-neon)' }}
      >
        <AutoAwesomeIcon size={26} />
      </span>
      <span className="px-2 text-center text-[13px] font-semibold text-textPrimary">
        Let AI choose
      </span>
      <SelectRing selected={selected} hovered={hovered} />
      {selected && <CheckBadge />}
    </button>
  );
}

// Template picker. Bigger, minimal grid of hover-playing previews. Selecting a
// template is optional ("Let AI choose" hands it to the backend parser). The
// options row below keeps a fixed height so picking a template never resizes
// the dialog.
export function TemplatePickerModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { data: templates, isLoading, isError } = useTemplates();
  const selectedName = useUiStore((s) => s.selectedTemplateName);
  const selectedTemplate = useUiStore((s) => s.selectedTemplate);
  const selectTemplate = useUiStore((s) => s.selectTemplate);
  const clearTemplate = useUiStore((s) => s.clearTemplate);

  const hasTags = !!selectedTemplate && selectedTemplate.tags.length > 0;

  return (
    <Modal open={open} onClose={onClose} width={900}>
      <div className="flex max-h-[86vh] flex-col">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold text-textPrimary">Template</h2>

        </div>

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
          {isLoading && (
            <div className="grid grid-cols-3 gap-3 md:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="aspect-9/16 w-full rounded-2xl" />
              ))}
            </div>
          )}
          {isError && (
            <div className="flex h-40 items-center justify-center text-error">
              <ErrorIcon size={28} />
            </div>
          )}
          {!isLoading && !isError && (
            <div className="grid grid-cols-3 gap-3 md:grid-cols-4">
              <AiChooseCard selected={!selectedName} onClick={clearTemplate} />
              {(templates ?? []).map((t) => (
                <TemplateCard
                  key={t.name}
                  template={t}
                  selected={selectedName === t.name}
                  onClick={() => selectTemplate(t)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Fixed-height options row: reserved so selecting a template doesn't
            change the dialog size. */}
        <div className="mt-4 flex min-h-20 flex-col justify-center border-t border-surface2 pt-4">
          {hasTags ? (
            <>
              <p className="mb-2 text-xs font-medium text-textSecondary">
                Options for {prettyTemplateName(selectedTemplate!.name)}
              </p>
              <TemplateTagPills template={selectedTemplate!} solid />
            </>
          ) : (
            <p className="text-xs text-textSecondary">
              {selectedTemplate
                ? 'This template has no extra options.'
                : 'The AI will pick a fitting template for your topic.'}
            </p>
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
