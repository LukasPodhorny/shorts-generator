import { ProfileSelector } from '@/components/generate/ProfileSelector';
import { CustomSlider } from '@/components/generate/CustomSlider';
import { TemplateCarousel } from '@/components/generate/TemplateCarousel';
import { BottomInputArea } from '@/components/generate/BottomInputArea';

// Ports the mobile VideoGeneratorScreen: avatar strip, reel-count slider, the
// template/video carousel, and the bottom prompt bar.
export function MobileGenerate() {
  return (
    <div className="flex h-full flex-col bg-background">
      <div className="pt-2.5" />
      <ProfileSelector />
      <CustomSlider />
      <div className="min-h-0 flex-1">
        <TemplateCarousel
          showArrows={false}
          tagScale={0.75}
          heightFraction={1}
          enlargeFactor={0.15}
        />
      </div>
      <BottomInputArea />
    </div>
  );
}
