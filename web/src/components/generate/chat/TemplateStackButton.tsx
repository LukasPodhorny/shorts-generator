import { useState } from 'react';
import { useTemplates } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import { SafeImage } from '@/components/ui/SafeImage';
import type { VideoTemplate } from '@/types/models';
import { prettyTemplateName } from './TemplatePickerModal';
import { AutoChip } from './AutoChip';

function Tile({
  template,
  front,
  hovered,
}: {
  template: VideoTemplate | null;
  front: boolean;
  hovered: boolean;
}) {
  // Two tiles fanned behind/in front of each other; they splay apart on hover.
  const base = front
    ? { rotate: 7, x: 3, y: 0, z: 2 }
    : { rotate: -11, x: -4, y: 0, z: 1 };
  const hov = front
    ? { rotate: 14, x: 6, y: -1 }
    : { rotate: -20, x: -8, y: -1 };
  const a = hovered ? { ...base, ...hov } : base;

  return (
    <span
      className="absolute overflow-hidden rounded-md bg-surface3"
      style={{
        width: 26,
        height: 37,
        zIndex: base.z,
        // The back card is dimmed so the front (active) one reads as primary.
        opacity: front ? 1 : 0.45,
        transform: `translate(${a.x}px, ${a.y}px) rotate(${a.rotate}deg)`,
        transformOrigin: 'bottom center',
        transition: 'transform 200ms cubic-bezier(0.34, 1.4, 0.64, 1)',
        boxShadow: '0 1px 3px rgba(0,0,0,0.4)',
      }}
    >
      {template?.thumbnailUrl && (
        <SafeImage url={template.thumbnailUrl} className="h-full w-full" />
      )}
    </span>
  );
}

// Minimal template control: a small fanned stack of template thumbnails that
// splays open on hover. The front card shows the selected template; when nothing
// is picked it previews the catalog and shows an "auto" hint so it's clear the
// AI will choose.
export function TemplateStackButton({ onClick }: { onClick: () => void }) {
  const { data: templates } = useTemplates();
  const selected = useUiStore((s) => s.selectedTemplate);
  const [hovered, setHovered] = useState(false);

  const list = templates ?? [];
  const front = selected ?? list[0] ?? null;
  const back = list.find((t) => t.name !== front?.name) ?? list[1] ?? null;

  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={selected ? `Template: ${prettyTemplateName(selected.name)}` : 'Choose a template'}
      aria-label="Choose a template"
      className="relative flex h-12 items-center justify-center"
    >
      <span className="relative flex h-12 w-14 items-center justify-center">
        <Tile template={back} front={false} hovered={hovered} />
        <Tile template={front} front hovered={hovered} />
      </span>
      {!selected && <AutoChip />}
    </button>
  );
}
