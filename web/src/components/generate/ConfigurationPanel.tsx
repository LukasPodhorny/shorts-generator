import { useUiStore } from '@/store/uiStore';
import { ReelCountSlider } from './ReelCountSlider';
import { AvatarSelectionGrid } from './AvatarSelectionGrid';

// Ports ConfigurationPanel: right-hand desktop column with the reel-count
// slider and avatar grid.
export function ConfigurationPanel() {
  const reelCount = useUiStore((s) => s.reelCount);
  const setReelCount = useUiStore((s) => s.setReelCount);

  return (
    <div className="flex h-full flex-col bg-surface1 p-6">
      <h2 className="text-xl font-semibold text-textPrimary">Configuration</h2>
      <div className="h-6" />
      <ReelCountSlider value={reelCount} min={0} max={7} onChange={setReelCount} />
      <div className="h-6" />
      <div className="min-h-0 flex-1">
        <AvatarSelectionGrid />
      </div>
      <div className="h-4" />
    </div>
  );
}
