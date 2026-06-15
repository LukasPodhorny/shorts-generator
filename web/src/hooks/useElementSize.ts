import { useCallback, useRef, useState } from 'react';

/**
 * Tracks an element's content-box size. Uses a callback ref so it works even
 * when the measured element mounts later (e.g. after a loading state), and
 * keeps the size updated via ResizeObserver. Returns a `ref` to spread onto
 * the element plus its current width/height.
 */
export function useElementSize<T extends HTMLElement>() {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const observerRef = useRef<ResizeObserver | null>(null);

  const ref = useCallback((node: T | null) => {
    observerRef.current?.disconnect();
    if (!node) return;

    const measure = () =>
      setSize((prev) => {
        const w = node.clientWidth;
        const h = node.clientHeight;
        return prev.width === w && prev.height === h ? prev : { width: w, height: h };
      });

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(node);
    observerRef.current = ro;
  }, []);

  return { ref, ...size };
}
