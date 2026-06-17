import { useCallback, useEffect, useRef, useState } from 'react';
import useEmblaCarousel from 'embla-carousel-react';
import type { EmblaCarouselType } from 'embla-carousel';
import { useTemplates } from '@/hooks/queries';
import { useUiStore } from '@/store/uiStore';
import { useElementSize } from '@/hooks/useElementSize';
import { Skeleton } from '@/components/ui/Skeleton';
import { MaskIcon } from '@/components/ui/MaskIcon';
import { TemplateCard } from './TemplateCard';
import { CarouselDots } from './CarouselDots';

const GAP = 20;
const DOTS_ROW = 50;
// How quickly cards shrink/fade away from center. base * snapCount means an
// adjacent card lands at the minimum scale.
const TWEEN_FACTOR_BASE = 1.0;
// Embla only enables looping when the slides comfortably exceed the viewport.
// With just a few templates we duplicate them so the loop is truly endless
// (like Flutter's enableInfiniteScroll). Each rendered slide maps back to a
// real template via modulo.
const MIN_SLIDES = 15;

const clamp01 = (n: number) => Math.min(1, Math.max(0, n));

function CarouselArrow({ flipped, onClick }: { flipped: boolean; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-full transition-colors"
      style={{ backgroundColor: hovered ? 'var(--color-surface3)' : 'rgba(34,34,34,0.8)' }}
    >
      <MaskIcon
        src="/icons/carousel_arrow.svg"
        size={20}
        color="var(--color-textPrimary)"
        style={{ transform: flipped ? 'scaleX(-1)' : undefined }}
      />
    </button>
  );
}

// Loading placeholder that mirrors the carousel layout: a centered row of 9:16
// card blocks (center one enlarged, neighbors shrunk/clipped) above a dots row.
function TemplateCarouselSkeleton({
  heightFraction = 0.82,
  enlargeFactor = 0.16,
}: {
  heightFraction?: number;
  enlargeFactor?: number;
}) {
  const { ref: areaRef, height: areaHeight } = useElementSize<HTMLDivElement>();
  const cardHeight = Math.max(120, Math.min(areaHeight * heightFraction, areaHeight - DOTS_ROW));
  const cardWidth = cardHeight * (9 / 16);
  const positions = [-2, -1, 0, 1, 2];
  const DOT_COUNT = 5;
  return (
    <div ref={areaRef} className="flex h-full w-full flex-col items-center justify-center">
      <div className="relative flex w-full items-center">
        <div className="w-full overflow-hidden">
          <div className="flex items-center justify-center" style={{ height: cardHeight }}>
            {positions.map((p) => {
              const centered = p === 0;
              const scale = 1 - enlargeFactor + enlargeFactor * (centered ? 1 : 0);
              return (
                <div
                  key={p}
                  className="flex shrink-0 items-center justify-center"
                  style={{ flex: `0 0 ${cardWidth + GAP}px` }}
                >
                  <Skeleton style={{ width: cardWidth, height: cardHeight, transform: `scale(${scale})`, borderRadius: 30 }} />
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center pt-4">
        {Array.from({ length: DOT_COUNT }).map((_, i) => (
          <Skeleton
            key={i}
            className="mx-[5px] rounded-lg"
            style={{ width: i === Math.floor(DOT_COUNT / 2) ? 28 : 10, height: 10 }}
          />
        ))}
      </div>
    </div>
  );
}

// Ports the desktop TemplateCarousel and mobile VideoCarousel into one adaptive
// component: an endlessly-looping, centered row of 9:16 template cards with the
// centered card enlarged + playing and page-indicator dots. Card scale, fade
// and the active dot update continuously while dragging.
export function TemplateCarousel({
  showArrows = true,
  tagScale = 1,
  heightFraction = 0.82,
  enlargeFactor = 0.16,
}: {
  showArrows?: boolean;
  tagScale?: number;
  heightFraction?: number;
  enlargeFactor?: number;
}) {
  const { data: templates, isLoading, isError, error, refetch, isFetching } = useTemplates();
  const selectTemplate = useUiStore((s) => s.selectTemplate);
  const selectedTemplateName = useUiStore((s) => s.selectedTemplateName);

  const real = templates ?? [];
  const R = real.length;
  const repeat = R === 0 ? 1 : Math.max(1, Math.ceil(MIN_SLIDES / R));
  const slides = repeat > 1 ? Array.from({ length: repeat }, () => real).flat() : real;
  const startIndex = Math.floor(repeat / 2) * R;

  const { ref: areaRef, height: areaHeight } = useElementSize<HTMLDivElement>();
  const [emblaRef, emblaApi] = useEmblaCarousel({
    loop: true,
    align: 'center',
    containScroll: false,
    startIndex,
  });

  // Raw (duplicated) slide index that is centered. realIndex = % R.
  const [selectedSlide, setSelectedSlide] = useState(startIndex);
  const [tweens, setTweens] = useState<number[]>([]);
  const tweenFactor = useRef(0);

  const applyTween = useCallback((api: EmblaCarouselType) => {
    const engine = api.internalEngine();
    const scrollProgress = api.scrollProgress();
    const next = api.scrollSnapList().map(() => 0);
    api.scrollSnapList().forEach((scrollSnap, snapIndex) => {
      let diffToTarget = scrollSnap - scrollProgress;
      engine.slideRegistry[snapIndex].forEach((slideIndex) => {
        if (engine.options.loop) {
          engine.slideLooper.loopPoints.forEach((loopItem) => {
            const target = loopItem.target();
            if (slideIndex === loopItem.index && target !== 0) {
              const sign = Math.sign(target);
              if (sign === -1) diffToTarget = scrollSnap - (1 + scrollProgress);
              if (sign === 1) diffToTarget = scrollSnap + (1 - scrollProgress);
            }
          });
        }
        next[slideIndex] = clamp01(1 - Math.abs(diffToTarget * tweenFactor.current));
      });
    });
    setTweens(next);
  }, []);

  const onSelect = useCallback((api: EmblaCarouselType) => {
    setSelectedSlide(api.selectedScrollSnap());
  }, []);

  useEffect(() => {
    if (!emblaApi) return;
    const onReInit = (api: EmblaCarouselType) => {
      tweenFactor.current = TWEEN_FACTOR_BASE * api.scrollSnapList().length;
      onSelect(api);
      applyTween(api);
    };
    onReInit(emblaApi);
    emblaApi.on('select', onSelect).on('scroll', applyTween).on('reInit', onReInit);
    return () => {
      emblaApi.off('select', onSelect).off('scroll', applyTween).off('reInit', onReInit);
    };
  }, [emblaApi, onSelect, applyTween]);

  // Push the centered template into the store on every settle.
  const realIndex = R > 0 ? selectedSlide % R : 0;
  useEffect(() => {
    if (R === 0) return;
    const t = real[realIndex];
    if (t && t.name !== selectedTemplateName) selectTemplate(t);
  }, [real, realIndex, R, selectedTemplateName, selectTemplate]);

  // Re-measure Embla when card size or slide count changes.
  const cardHeight = Math.max(120, Math.min(areaHeight * heightFraction, areaHeight - DOTS_ROW));
  const cardWidth = cardHeight * (9 / 16);
  useEffect(() => {
    emblaApi?.reInit();
  }, [emblaApi, cardWidth, slides.length]);

  if (isLoading) {
    return <TemplateCarouselSkeleton heightFraction={heightFraction} enlargeFactor={enlargeFactor} />;
  }
  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
        <p className="text-error">Couldn't load templates.</p>
        <p className="max-w-[420px] text-xs text-textSecondary">{String(error)}</p>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="rounded-full border border-textSecondary px-5 py-2 text-sm font-medium text-textPrimary transition-colors hover:bg-surface2 disabled:opacity-60"
        >
          {isFetching ? 'Retrying…' : 'Try again'}
        </button>
      </div>
    );
  }
  if (R === 0) {
    return (
      <div className="flex h-full items-center justify-center text-textSecondary">
        No templates available
      </div>
    );
  }

  // Active dot follows the card closest to center, continuously.
  const displaySlide =
    tweens.length === slides.length && slides.length > 0
      ? tweens.reduce((best, v, i, a) => (v > a[best] ? i : best), 0)
      : selectedSlide;
  const displayReal = displaySlide % R;

  const scrollToReal = (i: number) => {
    if (!emblaApi) return;
    const cur = selectedSlide;
    let delta = ((i - (cur % R)) % R + R) % R;
    if (delta > R / 2) delta -= R;
    emblaApi.scrollTo(cur + delta);
  };

  return (
    <div ref={areaRef} className="flex h-full w-full flex-col items-center justify-center">
      <div className="relative flex w-full items-center">
        <div className="w-full overflow-hidden" ref={emblaRef}>
          <div className="flex items-center" style={{ height: cardHeight }}>
            {slides.map((template, i) => {
              const tween = tweens[i] ?? (i === selectedSlide ? 1 : 0);
              const isSelected = i === selectedSlide;
              const scale = 1 - enlargeFactor + enlargeFactor * tween;
              const fadeOpacity = Math.min(0.6, (1 - tween) * 0.6);
              return (
                <div
                  key={`${template.id}-${i}`}
                  className="flex shrink-0 items-center justify-center"
                  style={{ flex: `0 0 ${cardWidth + GAP}px` }}
                >
                  <div style={{ width: cardWidth, height: cardHeight, transform: `scale(${scale})` }}>
                    <TemplateCard
                      template={template}
                      isSelected={isSelected}
                      fadeOpacity={fadeOpacity}
                      tagScale={tagScale}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {showArrows && (
          <>
            <div className="absolute left-4 top-1/2 -translate-y-1/2">
              <CarouselArrow flipped onClick={() => emblaApi?.scrollPrev()} />
            </div>
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <CarouselArrow flipped={false} onClick={() => emblaApi?.scrollNext()} />
            </div>
          </>
        )}
      </div>

      <div className="flex items-center justify-center pt-4">
        <CarouselDots count={R} selectedIndex={displayReal} onDotClick={scrollToReal} />
      </div>
    </div>
  );
}
