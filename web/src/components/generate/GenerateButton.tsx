import { useUiStore } from '@/store/uiStore';
import { CreditIcon } from '@/components/ui/MaskIcon';
import { Spinner } from '@/components/ui/Spinner';

// Neon stadium "generate" button showing the total cost (template credits ×
// reel count) and a credit icon, or a spinner while generating.
export function GenerateButton({
  disabled,
  generating,
  onClick,
}: {
  disabled: boolean;
  generating: boolean;
  onClick: () => void;
}) {
  const template = useUiStore((s) => s.selectedTemplate);
  const reelCount = useUiStore((s) => s.reelCount);
  const totalCost = template ? template.credits * reelCount : 0;

  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      className="flex min-w-[75px] cursor-pointer items-center justify-center rounded-full bg-neon px-2 py-3 text-surface1"
    >
      <span className="flex h-[19px] items-center justify-center">
        {generating ? (
          <Spinner size={19} strokeWidth={2} className="text-surface1" />
        ) : (
          <span className="flex items-center gap-1">
            <span className="text-base font-bold leading-none">{totalCost}</span>
            <CreditIcon size={12} color="var(--color-surface1)" />
          </span>
        )}
      </span>
    </button>
  );
}
