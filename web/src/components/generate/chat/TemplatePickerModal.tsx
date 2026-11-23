import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { ErrorIcon } from '@/components/ui/icons';
import { CarouselVideoPlayer } from '@/components/generate/CarouselVideoPlayer';
import { TemplateTagPills } from '@/components/generate/TemplateTagPills';
import { useTemplates } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import type { VideoTemplate } from '@/types/models';

export function prettyTemplateName(name: string): string {
  const cleaned = name.replace(/[-_]+/g, ' ').trim();
  return cleaned.replace(/\b\w/g, (c) => c.toUpperCase());
}

const captions: Record<string, string> = {
  static_gameplay: 'Gameplay with a still avatar',
  basic_gameplay: 'Gameplay with an avatar',
  static_gameplay_v2: 'An updated static gameplay look',
  stock_story: 'Full-screen footage with voiceover',
  lecture: 'Clean visuals for deeper lessons',
  documentary: 'Real-world footage and notes',
  briefing: 'A quick visual explainer',
  math: 'Math lessons with full-screen animation',
};

function isLandscape(template: VideoTemplate): boolean {
  return (template.width ?? 1080) > (template.height ?? 1920);
}

function SelectedCheck() {
  return (
    <span className="grid size-5.5 place-items-center rounded-full bg-neon text-[#102010] shadow-[0_2px_8px_rgba(0,0,0,0.5)]">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="m4 10 4 4 8-8" stroke="black" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
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
  const [previewing, setPreviewing] = useState(false);
  const landscape = isLandscape(template);

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setPreviewing(true)}
      onMouseLeave={() => setPreviewing(false)}
      onFocus={() => setPreviewing(true)}
      onBlur={() => setPreviewing(false)}
      aria-pressed={selected}
      title={template.description || prettyTemplateName(template.name)}
      className={`relative block w-full min-w-0 overflow-hidden rounded-2xl border bg-[#101713] text-left transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-neon ${landscape ? 'aspect-video' : 'aspect-9/16'} ${selected ? 'border-2 border-neon hover:border-neon' : 'border-2 border-white/10 hover:border-white/40'
        }`}
    >
      <CarouselVideoPlayer
        videoUrl={template.previewUrl}
        thumbnailUrl={template.thumbnailUrl ?? ''}
        isSelected={previewing}
        fit="cover"
      />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-linear-to-b from-black/40 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-linear-to-t from-black/85 via-black/35 to-transparent" />
      {selected && <span className="absolute left-1.5 top-1.5"><SelectedCheck /></span>}
      <span className="absolute right-3 top-3 flex items-center gap-1 text-xs font-semibold text-white drop-shadow-[0_1px_4px_rgba(0,0,0,0.9)]">
        {template.credits}<CreditIcon size={10} color="#ffffff" />
      </span>
      <div className="absolute inset-x-0 bottom-0 px-3 pb-3 text-white" style={{ textShadow: '0 1px 8px rgba(0,0,0,0.8)' }}>
        <span className="block truncate text-xs font-semibold sm:text-sm">
          {prettyTemplateName(template.name)}
        </span>
        <span className="mt-0.5 block truncate text-[10px] text-white/80 sm:text-[11px]">
          {captions[template.name] ?? template.description ?? (landscape ? 'Landscape video' : 'Portrait video')}
        </span>
      </div>
    </button>
  );
}

function AutoSelectButton({ selected, onClick }: { selected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      role="switch"
      aria-checked={selected}
      className="inline-flex shrink-0 items-center gap-2.5 rounded-lg px-1 py-1.5 text-sm font-medium text-textPrimary hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-neon"
    >
      Auto select
      <span className={`relative h-5 w-9 rounded-full transition-colors ${selected ? 'bg-neon' : 'bg-surface4'}`} aria-hidden="true">
        <span className={`absolute left-0 top-[3px] size-3.5 rounded-full bg-white shadow-sm transition-transform ${selected ? 'translate-x-[19px]' : 'translate-x-[3px]'}`} />
      </span>
    </button>
  );
}

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
  const portraitTemplates = (templates ?? []).filter((template) => !isLandscape(template));
  const landscapeTemplates = (templates ?? []).filter(isLandscape);
  const hasTags = !!selectedTemplate && selectedTemplate.tags.length > 0;

  return (
    <Modal open={open} onClose={onClose} width={980} flushBottom>
      <div className="relative flex max-h-[90vh] flex-col">
        <div className="shrink-0">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-textPrimary">Choose a template</h2>
            <AutoSelectButton selected={!selectedName} onClick={clearTemplate} />
          </div>
          {hasTags && (
            <div className="mt-3">
              <p className="mb-2 text-xs font-medium text-textSecondary">
                Options for {prettyTemplateName(selectedTemplate!.name)}
              </p>
              <TemplateTagPills template={selectedTemplate!} solid />
            </div>
          )}
        </div>

        <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
          {isLoading && (
            <div className="mx-auto grid max-w-[976px] grid-cols-2 gap-3 sm:max-w-[482px] lg:max-w-[976px] lg:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="aspect-9/16 w-full rounded-2xl" />
              ))}
            </div>
          )}
          {isError && (
            <div className="flex h-32 items-center justify-center gap-2 text-sm text-error">
              <ErrorIcon size={22} /> Could not load templates
            </div>
          )}
          {!isLoading && !isError && (
            <>
              {portraitTemplates.length > 0 && (
                <div className="mx-auto grid max-w-[976px] grid-cols-2 gap-3 sm:max-w-[482px] lg:max-w-[976px] lg:grid-cols-4">
                  {portraitTemplates.map((template) => (
                    <TemplateCard
                      key={template.name}
                      template={template}
                      selected={selectedName === template.name}
                      onClick={() => selectTemplate(template)}
                    />
                  ))}
                </div>
              )}
              {landscapeTemplates.length > 0 && (
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {landscapeTemplates.map((template) => (
                    <TemplateCard
                      key={template.name}
                      template={template}
                      selected={selectedName === template.name}
                      onClick={() => selectTemplate(template)}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <button
          type="button"
          onClick={onClose}
          className="absolute bottom-5 right-0 z-10 rounded-full bg-neon px-6 py-2.5 text-sm font-semibold text-[#102010] shadow-[0_6px_20px_rgba(0,0,0,0.65)] transition-colors hover:bg-[#55e258] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-neon"
        >
          Done
        </button>
      </div>
    </Modal>
  );
}
