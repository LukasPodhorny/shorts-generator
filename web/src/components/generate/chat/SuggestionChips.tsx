import { useState, type ReactNode } from 'react';
import { QuizIcon, TemplateIcon, SparkleIcon } from '@/components/ui/icons';

interface Suggestion {
  icon: ReactNode;
  label: string;
  prompt: string;
}

const SUGGESTIONS: Suggestion[] = [
  {
    icon: <SparkleIcon size={16} />,
    label: 'Explain a topic',
    prompt: 'Make a reel explaining how black holes work, for a curious beginner.',
  },
  {
    icon: <QuizIcon size={16} />,
    label: 'With quiz',
    prompt: 'Make one reel about photosynthesis and end it with a short quiz.',
  },
  {
    icon: <TemplateIcon size={16} />,
    label: 'Math lesson',
    prompt: 'Explain the slope of a curve with a worked example and full-screen animation.',
  },
];

function Chip({ suggestion, onClick }: { suggestion: Suggestion; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="flex items-center gap-2 rounded-full px-3.5 py-2 text-sm font-medium text-textSecondary"
      style={{
        backgroundColor: hovered ? 'var(--color-surface2)' : 'transparent',
        border: '1px solid var(--color-surface2)',
        transition: 'background-color 150ms ease',
      }}
    >
      <span className="text-textPrimary/70">{suggestion.icon}</span>
      {suggestion.label}
    </button>
  );
}

// Starter prompts shown under the empty composer, like a typical chat landing.
export function SuggestionChips({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {SUGGESTIONS.map((s) => (
        <Chip key={s.label} suggestion={s} onClick={() => onPick(s.prompt)} />
      ))}
    </div>
  );
}
