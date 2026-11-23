import { useEffect, useRef } from 'react';

const SPACING = 26;
const REACH = 260;

type Dot = { x: number; y: number; seed: number };

// A quiet pixel field that bends and lights up around the pointer.
export function ReactiveGenerateBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !parent || !ctx) return;

    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const pointer = { x: 0, y: 0, targetX: 0, targetY: 0, active: false, strength: 0 };
    const wake = { x: 0, y: 0 };
    let dots: Dot[] = [];
    let width = 0;
    let height = 0;
    let frame = 0;

    const draw = (now: number) => {
      const time = now / 1000;
      const moving = !motion.matches;
      if (moving) {
        pointer.x += (pointer.targetX - pointer.x) * 0.18;
        pointer.y += (pointer.targetY - pointer.y) * 0.18;
        wake.x += (pointer.x - wake.x) * 0.07;
        wake.y += (pointer.y - wake.y) * 0.07;
        pointer.strength += ((pointer.active ? 1 : 0) - pointer.strength) * 0.08;
      }

      ctx.clearRect(0, 0, width, height);
      if (pointer.strength > 0.01) {
        const halo = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 280);
        halo.addColorStop(0, `rgba(52, 203, 54, ${0.045 * pointer.strength})`);
        halo.addColorStop(1, 'rgba(52, 203, 54, 0)');
        ctx.fillStyle = halo;
        ctx.fillRect(pointer.x - 280, pointer.y - 280, 560, 560);
      }

      const sweepX = width * (0.55 + 0.3 * Math.sin(time * 0.25));
      for (const dot of dots) {
        const dx = dot.x - pointer.x;
        const dy = dot.y - pointer.y;
        const distance = Math.hypot(dx, dy) || 1;
        const influence = moving ? Math.max(0, 1 - distance / REACH) ** 2 * pointer.strength : 0;
        const wakeDistance = Math.hypot(dot.x - wake.x, dot.y - wake.y);
        const afterglow = moving ? Math.max(0, 1 - wakeDistance / 300) ** 2 * pointer.strength : 0;
        const sweep = moving ? Math.max(0, 1 - Math.abs(dot.x - sweepX) / 280) ** 2 * 0.18 : 0;
        const light = influence * 0.9 + afterglow * 0.22 + sweep;
        const x = dot.x + (dx / distance) * influence * 22;
        const y = dot.y + (dy / distance) * influence * 22;
        const size = 1.1 + dot.seed * 0.6 + influence * 1.5;

        ctx.fillStyle = light > 0.015
          ? `rgba(52, 203, 54, ${Math.min(0.9, 0.12 + light)})`
          : `rgba(130, 151, 133, ${0.11 + dot.seed * 0.05})`;
        ctx.fillRect(x, y, size, size);
      }

      if (moving) frame = requestAnimationFrame(draw);
    };

    const resize = () => {
      cancelAnimationFrame(frame);
      const bounds = parent.getBoundingClientRect();
      width = bounds.width;
      height = bounds.height;
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(height * scale);
      ctx.setTransform(scale, 0, 0, scale, 0, 0);
      dots = [];
      for (let row = -1; row <= Math.ceil(height / SPACING); row++) {
        for (let col = -1; col <= Math.ceil(width / SPACING); col++) {
          const seed = (Math.sin(col * 127.1 + row * 311.7) * 43758.5453) % 1;
          const random = Math.abs(seed);
          dots.push({
            x: col * SPACING + (row % 2) * SPACING / 2 + (random - 0.5) * 5,
            y: row * SPACING + (random - 0.5) * 5,
            seed: random,
          });
        }
      }
      draw(performance.now());
    };

    const onPointerMove = (event: PointerEvent) => {
      if (motion.matches) return;
      const bounds = parent.getBoundingClientRect();
      pointer.targetX = event.clientX - bounds.left;
      pointer.targetY = event.clientY - bounds.top;
      if (!pointer.active && pointer.strength < 0.01) {
        pointer.x = wake.x = pointer.targetX;
        pointer.y = wake.y = pointer.targetY;
      }
      pointer.active = true;
    };
    const onPointerLeave = () => { pointer.active = false; };
    const onMotionChange = () => {
      cancelAnimationFrame(frame);
      pointer.strength = 0;
      draw(performance.now());
    };

    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    parent.addEventListener('pointermove', onPointerMove);
    parent.addEventListener('pointerleave', onPointerLeave);
    motion.addEventListener('change', onMotionChange);
    resize();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      parent.removeEventListener('pointermove', onPointerMove);
      parent.removeEventListener('pointerleave', onPointerLeave);
      motion.removeEventListener('change', onMotionChange);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ clipPath: 'inset(0 0 0 calc(clamp(260px, 14vw, 340px) - 28px))' }}
    />
  );
}
