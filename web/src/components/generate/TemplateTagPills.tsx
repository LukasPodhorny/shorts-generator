import { useState, type ReactNode } from 'react';
import type { VideoTemplate } from '@/types/models';
import { useUiStore } from '@/store/uiStore';

// Tag glyphs (Material Symbols equivalents for manim/quiz/generic).
const FunctionsIcon = ({ size }: { size: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M18 4H6v2l6.5 6L6 18v2h12v-3h-7l5-5-5-5h7z" />
  </svg>
);
const QuizIcon = ({ size }: { size: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M11.07 12.85c.77-1.39 2.25-2.21 3.11-3.44.91-1.29.4-3.7-2.18-3.7-1.69 0-2.52 1.28-2.87 2.34L6.54 6.96C7.25 4.83 9.18 3 11.99 3c2.35 0 3.96 1.07 4.78 2.41.7 1.15 1.11 3.3.03 4.9-1.2 1.77-2.35 2.31-2.97 3.45-.25.46-.35.76-.35 2.24h-2.89c-.01-.78-.13-2.05.45-3.15M14 20a2 2 0 1 1-4 0 2 2 0 0 1 4 0" />
  </svg>
);
const SparkleIcon = ({ size }: { size: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
    <path d="M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25zM11.5 9.5 9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25z" />
  </svg>
);
// A compact contained toggle switch: the knob sits inside the track. The track
// fills with the tag color and the knob slides right when on.
function MiniSwitch({ on, color, scale }: { on: boolean; color: string; scale: number }) {
  const trackW = 22 * scale;
  const trackH = 13 * scale;
  const pad = 1 * scale;
  const knobD = trackH - pad * 2;
  return (
    <span
      aria-hidden
      style={{
        position: 'relative',
        width: trackW,
        height: trackH,
        flexShrink: 0,
        borderRadius: trackH,
        backgroundColor: on ? color : 'rgba(255,255,255,0.25)',
        transition: 'background-color 160ms ease',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: pad,
          left: pad,
          width: knobD,
          height: knobD,
          borderRadius: '50%',
          backgroundColor: '#ffffff',
          boxShadow: '0 1px 2px rgba(0,0,0,0.4)',
          transform: on ? `translateX(${trackW - knobD - pad * 2}px)` : 'translateX(0)',
          transition: 'transform 170ms cubic-bezier(0.4,0,0.2,1)',
        }}
      />
    </span>
  );
}

interface TagStyle {
  icon: (p: { size: number }) => ReactNode;
  color: string;
  label: string;
}

function titleCase(s: string) {
  return s ? s[0].toUpperCase() + s.slice(1) : s;
}

function styleFor(assetType: string): TagStyle {
  if (assetType === 'manim') return { icon: FunctionsIcon, color: '#7C5CFF', label: 'Manim' };
  if (assetType === 'question') return { icon: QuizIcon, color: '#FFA726', label: 'Quiz' };
  return { icon: SparkleIcon, color: '#4FC3F7', label: titleCase(assetType) };
}

function defaultEnabledSet(template: VideoTemplate): Set<string> {
  return new Set(template.tags.filter((t) => t.defaultEnabled).map((t) => t.assetType));
}

// A dark-glass pill with a leading toggle switch and the feature label, matching
// the reference style. Whole chip is the click target; the switch state and label
// brightness convey on/off.
function Pill({
  style,
  enabled,
  scale,
  onClick,
}: {
  style: TagStyle;
  enabled: boolean;
  scale: number;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const title = enabled
    ? `${style.label} on — click to turn off`
    : `${style.label} off — click to turn on`;

  return (
    <button
      type="button"
      title={title}
      aria-pressed={enabled}
      onClick={(e) => {
        // Don't let the toggle bubble into the carousel's drag/select handlers.
        e.stopPropagation();
        onClick();
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="inline-flex cursor-pointer items-center rounded-full"
      style={{
        padding: `${8 * scale}px ${13 * scale}px ${8 * scale}px ${8 * scale}px`,
        gap: 6 * scale,
        backgroundColor: hovered ? 'rgba(20,20,20,0.72)' : 'rgba(20,20,20,0.6)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        transition: 'background-color 150ms ease',
      }}
    >
      <MiniSwitch on={enabled} color={style.color} scale={scale} />
      <span
        style={{
          fontSize: 13 * scale,
          fontWeight: 600,
          lineHeight: 1,
          color: enabled ? '#ffffff' : 'rgba(255,255,255,0.7)',
        }}
      >
        {style.label}
      </span>
    </button>
  );
}

// Ports TemplateTagPills: per-template toggleable asset tags overlaid on the
// carousel card. Selection persists in the ui store.
export function TemplateTagPills({
  template,
  scale = 1,
}: {
  template: VideoTemplate;
  scale?: number;
}) {
  const enabledMap = useUiStore((s) => s.enabledTagsByTemplate);
  const setEnabledTags = useUiStore((s) => s.setEnabledTags);

  if (template.tags.length === 0) return null;

  const enabled = enabledMap[template.name] ?? defaultEnabledSet(template);

  return (
    <div className="flex flex-wrap" style={{ gap: 3 * scale }}>
      {template.tags.map((tag) => (
        <Pill
          key={tag.assetType}
          style={styleFor(tag.assetType)}
          enabled={enabled.has(tag.assetType)}
          scale={scale}
          onClick={() => {
            const current = new Set(enabledMap[template.name] ?? defaultEnabledSet(template));
            if (current.has(tag.assetType)) current.delete(tag.assetType);
            else current.add(tag.assetType);
            setEnabledTags(template.name, current);
          }}
        />
      ))}
    </div>
  );
}
