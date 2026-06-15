import { TemplateCarousel } from '@/components/generate/TemplateCarousel';
import { PromptInputPanel } from '@/components/generate/PromptInputPanel';
import { ConfigurationPanel } from '@/components/generate/ConfigurationPanel';

// Ports DesktopGenerateScreen: left column = template carousel over the prompt
// input; right column = the configuration panel. The config width scales with
// the viewport (clamp 320–440), matching screenWidth * 0.175 in Flutter.
export function DesktopGenerate() {
  return (
    <div className="flex h-full w-full bg-background">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <div className="min-h-0 flex-1">
          <TemplateCarousel showArrows tagScale={1} heightFraction={0.82} enlargeFactor={0.16} />
        </div>
        <PromptInputPanel />
      </div>
      <div style={{ width: 'clamp(320px, 17.5vw, 440px)' }}>
        <ConfigurationPanel />
      </div>
    </div>
  );
}
