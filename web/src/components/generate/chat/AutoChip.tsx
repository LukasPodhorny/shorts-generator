// A tiny "auto" badge pinned to the bottom-left corner of the template/avatar
// controls, signalling the AI will choose when the user hasn't picked one.
// Anchored to the (equal-height) button so both controls share the same Y.
export function AutoChip() {
  return (
    <span className="pointer-events-none absolute -bottom-1.5 -left-1 z-20 rounded-full border border-surface1 bg-background px-1.5 text-[12px] leading-4 text-textPrimary opacity-50">
      auto
    </span>
  );
}
