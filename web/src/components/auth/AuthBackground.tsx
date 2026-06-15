import { useEffect, useRef } from 'react';

// Port of the Flutter _MarbledPainter: soft, marbled horizontal bands drawn on
// a canvas. The pattern is sized against a virtual reference canvas so smaller
// viewports crop it instead of squishing.
const BASE = '#141414';
const PALETTE = [
  BASE,
  'rgba(27,34,48,0.43)',
  'rgba(30,22,22,0.43)',
  'rgba(35,27,44,0.43)',
];
const VW = 1600;
const VBH = 170;

function wave(virtualX: number, seed: number): number {
  const s1 = Math.sin((virtualX / VW) * Math.PI * 1.3 + seed * 0.9);
  const s2 = Math.sin((virtualX / VW) * Math.PI * 3.2 + seed * 1.7);
  const s3 = Math.sin((virtualX / VW) * Math.PI * 7.0 + seed * 2.3);
  return s1 * VBH * 0.55 + s2 * VBH * 0.18 + s3 * VBH * 0.06;
}

export function AuthBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const draw = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const w = parent.clientWidth;
      const h = parent.clientHeight;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.scale(dpr, dpr);

      ctx.fillStyle = BASE;
      ctx.fillRect(0, 0, w, h);

      const xOffset = (VW - w) / 2;
      const bandCount = Math.ceil(h / VBH) + 2;
      for (let i = -1; i <= bandCount; i++) {
        const topY = i * VBH;
        const bottomY = (i + 1) * VBH;
        ctx.beginPath();
        ctx.moveTo(-24, topY + wave(-24 + xOffset, i));
        for (let x = -24; x <= w + 24; x += 6) ctx.lineTo(x, topY + wave(x + xOffset, i));
        for (let x = w + 24; x >= -24; x -= 6) ctx.lineTo(x, bottomY + wave(x + xOffset, i + 1));
        ctx.closePath();
        const idx = ((i % PALETTE.length) + PALETTE.length) % PALETTE.length;
        ctx.fillStyle = PALETTE[idx];
        ctx.fill();
      }
    };

    draw();
    const ro = new ResizeObserver(draw);
    if (canvas.parentElement) ro.observe(canvas.parentElement);
    return () => ro.disconnect();
  }, []);

  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />;
}
