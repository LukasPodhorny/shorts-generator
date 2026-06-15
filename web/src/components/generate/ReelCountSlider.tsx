import { useCallback, useRef, useState } from 'react';

// Ports ReelCountSlider: a custom horizontal slider (track + neon fill +
// growing thumb with inner dot and drag glow). Integer value, min..max, but
// never below 1 (matching the Flutter clamp).
export function ReelCountSlider({
  value,
  min,
  max,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const steps = max - min;
  const fraction = (value - min) / steps;

  const updateFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const raw = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      let next = min + Math.round(raw * steps);
      next = Math.max(1, Math.min(max, next));
      if (next !== value) onChange(next);
    },
    [min, max, steps, value, onChange],
  );

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    setDragging(true);
    updateFromClientX(e.clientX);
  };

  return (
    <div className="flex items-center">
      <div className="flex-1">
        {/* 8px horizontal padding matches the Flitter track inset */}
        <div
          className="relative cursor-pointer px-2 py-[14px]"
          onPointerDown={onPointerDown}
          onPointerMove={(e) => dragging && updateFromClientX(e.clientX)}
          onPointerUp={() => setDragging(false)}
          onPointerCancel={() => setDragging(false)}
        >
          <div ref={trackRef} className="relative h-1 w-full rounded-full bg-surface3">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-neon"
              style={{ width: `${fraction * 100}%` }}
            />
            {/* Thumb */}
            <div
              className="absolute top-1/2 flex items-center justify-center rounded-full bg-textPrimary shadow-[0_1px_3px_rgba(0,0,0,0.35)] transition-transform"
              style={{
                left: `${fraction * 100}%`,
                width: 16,
                height: 16,
                transform: `translate(-50%, -50%) scale(${dragging ? 1.35 : 1})`,
              }}
            >
              {dragging && (
                <span className="absolute h-6 w-6 rounded-full bg-neon/20" />
              )}
              <span className="h-[5.6px] w-[5.6px] rounded-full bg-neon" />
            </div>
          </div>
        </div>
      </div>
      <span className="ml-3 text-sm font-semibold text-textPrimary">{value} reels</span>
    </div>
  );
}
