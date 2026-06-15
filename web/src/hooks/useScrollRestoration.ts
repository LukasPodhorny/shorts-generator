import { useCallback, useLayoutEffect, useRef } from 'react';

// Module-level store so positions survive a component unmount/remount (e.g.
// navigating into a series detail and back) without leaking into React state.
const positions = new Map<string, number>();

/**
 * Remembers the vertical scroll offset of a scrollable container across
 * mounts, keyed by a stable string. Attach the returned `ref` to the element
 * that has `overflow-y-auto` and wire `onScroll` to it.
 *
 * The offset is recorded continuously from `onScroll` (never on unmount: a
 * detach-time read can capture a clamped/transient value — e.g. under React
 * StrictMode's double ref-invocation — and clobber the real position with 0).
 *
 * On remount the saved offset is restored synchronously on attach (no visible
 * jump when the cached content is already tall enough) and then re-applied for
 * a few frames, because the grid measures its column count asynchronously and
 * the container isn't at its final height on the first frame.
 */
export function useScrollRestoration<T extends HTMLElement>(key: string) {
  const elRef = useRef<T | null>(null);

  const ref = useCallback(
    (node: T | null) => {
      elRef.current = node;
      if (node) {
        const saved = positions.get(key);
        if (saved != null) node.scrollTop = saved;
      }
    },
    [key],
  );

  useLayoutEffect(() => {
    const target = positions.get(key);
    if (target == null) return;
    let raf = 0;
    let tries = 0;
    const apply = () => {
      const el = elRef.current;
      if (el) {
        el.scrollTop = target;
        // Keep re-applying until the offset sticks (the content may still be
        // growing as columns/heights settle), with a hard cap so we never spin
        // when the target is genuinely unreachable (fewer items than before).
        if (Math.abs(el.scrollTop - target) > 1 && tries++ < 20) {
          raf = requestAnimationFrame(apply);
          return;
        }
      }
    };
    raf = requestAnimationFrame(apply);
    return () => cancelAnimationFrame(raf);
  }, [key]);

  const onScroll = useCallback(
    (e: React.UIEvent<T>) => {
      positions.set(key, e.currentTarget.scrollTop);
    },
    [key],
  );

  return { ref, onScroll };
}
