import { useCallback, useRef, useState } from 'react';
import { useUiStore } from '@/store/uiStore';

// Ports the mobile CustomSlider: a thick (7px) track with a thumb that morphs
// from a 19×19 circle to a 10×28 pill while dragging. Value 1..7.
export function CustomSlider() {
  const value = useUiStore((s) => s.reelCount);
  const setReelCount = useUiStore((s) => s.setReelCount);
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  const min = 0;
  const max = 7;
  const steps = max - min;
  const fraction = (value - min) / steps;

  const updateFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const raw = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      const next = Math.max(1, Math.min(max, min + Math.round(raw * steps)));
      if (next !== value) setReelCount(next);
    },
    [value, setReelCount, steps],
  );

  return (
    <div className="flex items-center py-[13.5px] pl-[15px] pr-[25px]">
      <div className="flex-1">
        <div
          className="relative cursor-pointer py-[14px]"
          onPointerDown={(e) => {
            (e.target as Element).setPointerCapture?.(e.pointerId);
            setDragging(true);
            updateFromClientX(e.clientX);
          }}
          onPointerMove={(e) => dragging && updateFromClientX(e.clientX)}
          onPointerUp={() => setDragging(false)}
          onPointerCancel={() => setDragging(false)}
        >
          <div ref={trackRef} className="relative h-[7px] w-full rounded-full bg-surface1">
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-neon"
              style={{ width: `${fraction * 100}%` }}
            />
            <div
              className="absolute top-1/2 rounded-full bg-textPrimary transition-all duration-150"
              style={{
                left: `${fraction * 100}%`,
                width: dragging ? 10 : 19,
                height: dragging ? 28 : 19,
                transform: 'translate(-50%, -50%)',
              }}
            />
          </div>
        </div>
      </div>
      <span className="ml-2 text-base font-bold text-white">{value} reels</span>
    </div>
  );
}
