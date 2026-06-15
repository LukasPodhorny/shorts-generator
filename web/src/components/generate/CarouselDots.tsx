// Animated page-indicator dots: active dot stretches to a pill (ports the
// AnimatedContainer dot row used by both carousels).
export function CarouselDots({
  count,
  selectedIndex,
  onDotClick,
}: {
  count: number;
  selectedIndex: number;
  onDotClick: (index: number) => void;
}) {
  return (
    <div className="flex items-center justify-center">
      {Array.from({ length: count }).map((_, i) => {
        const active = i === selectedIndex;
        return (
          <button
            key={i}
            type="button"
            onClick={() => onDotClick(i)}
            className="mx-[5px] h-[10px] rounded-lg transition-all duration-300 ease-out"
            style={{
              width: active ? 28 : 10,
              backgroundColor: active
                ? 'var(--color-textPrimary)'
                : 'var(--color-surface1)',
            }}
            aria-label={`Go to slide ${i + 1}`}
          />
        );
      })}
    </div>
  );
}
