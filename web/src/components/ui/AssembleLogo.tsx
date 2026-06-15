// Self-contained port of the "Assemble" logo bumper (pdftoreel brand mark).
// The mark builds in sequence — ring eases in, disc grows from the centre,
// sparkle punches in with a soft overshoot — then the wordmark fades up.
// Runs its own rAF loop and seamlessly loops via a short fade-out, so it
// works as a lively replacement for a plain spinner on the splash screen.
import { useEffect, useRef, useState } from 'react';

const GREEN = '#34CB36';
// Knockout colour for the sparkle — matches the splash background so the
// sparkle reads as a cut-out of the green disc.
const KNOCKOUT = '#0f0f0f';

const RING_D =
  'M580.815 0C945.777 0.000312652 1024 78.223 1024 443.185V580.815C1024 945.777 945.777 1024 580.815 1024H443.185C78.223 1024 0.000312573 945.777 0 580.815V443.185C0.000312652 78.223 78.223 0.000312573 443.185 0H580.815ZM457.79 87.04C156.694 87.04 92.16 151.574 92.16 452.67V566.21C92.16 867.306 156.694 931.84 457.79 931.84H571.33C872.426 931.84 936.96 867.306 936.96 566.21V452.67C936.96 151.574 872.426 87.04 571.33 87.04H457.79Z';
const SPARKLE_D =
  'M569.62 360.52C549.826 307.03 474.174 307.03 454.38 360.52L438.83 402.535C432.607 419.35 419.35 432.607 402.535 438.83L360.52 454.38C307.03 474.174 307.03 549.826 360.52 569.62L402.535 585.17C419.35 591.393 432.607 604.65 438.83 621.465L454.38 663.48C474.174 716.97 549.826 716.97 569.62 663.48L585.17 621.465C591.393 604.65 604.65 591.393 621.465 585.17L663.48 569.62C716.97 549.826 716.97 474.174 663.48 454.38L621.465 438.83C604.65 432.607 591.393 419.35 585.17 402.535L569.62 360.52Z';

const CX = 512;
const CY = 512;

const easeOutCubic = (t: number) => --t * t * t + 1;
const easeOutBack = (t: number) => {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};

const lerp = (a: number, b: number, p: number) => a + (b - a) * p;

// Eased progress over the window [s, e].
function seg(t: number, s: number, e: number, ease = easeOutCubic) {
  if (t <= s) return 0;
  if (t >= e) return 1;
  return ease((t - s) / (e - s));
}

type Part = { tx?: number; ty?: number; scale?: number; rotate?: number };
function around(cx: number, cy: number, { tx = 0, ty = 0, scale = 1, rotate = 0 }: Part = {}) {
  return `translate(${cx + tx} ${cy + ty}) rotate(${rotate}) scale(${scale}) translate(${-cx} ${-cy})`;
}

// Loop timing (seconds): build → brief hold → fade out → restart.
const LOOP = 2.7;
const FADE_START = 2.3;

export function AssembleLogo({ size = 132 }: { size?: number }) {
  const [t, setT] = useState(0);
  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced) {
      // Hold the fully-assembled mark; skip the animation loop.
      setT(LOOP - 0.4);
      return;
    }

    const step = (ts: number) => {
      if (startRef.current == null) startRef.current = ts;
      const elapsed = ((ts - startRef.current) / 1000) % LOOP;
      setT(elapsed);
      rafRef.current = requestAnimationFrame(step);
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // Part choreography (mirrors the original Assemble direction).
  const ringP = seg(t, 0.0, 0.75);
  const discP = seg(t, 0.35, 1.05);
  const sparkP = seg(t, 0.78, 1.28, easeOutBack);
  const sparkOpacity = seg(t, 0.78, 1.05);
  const wordP = seg(t, 1.25, 1.85);

  // Seamless loop: fade the whole lockup out before it snaps back to t=0.
  const groupOpacity = 1 - seg(t, FADE_START, LOOP);

  const ring = { opacity: ringP, scale: lerp(1.14, 1, ringP) };
  const disc = { opacity: discP, scale: lerp(0.5, 1, discP) };
  const sparkle = { opacity: sparkOpacity, scale: sparkP, rotate: lerp(-45, 0, sparkP) };

  return (
    <div
      role="status"
      aria-label="Loading"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: size * 0.28,
        opacity: groupOpacity,
      }}
    >
      <svg width={size} height={size} viewBox="0 0 1024 1024" style={{ overflow: 'visible', display: 'block' }}>
        {/* Disc */}
        <g opacity={disc.opacity} transform={around(CX, CY, disc)}>
          <circle cx={CX} cy={CY} r={307.2} fill={GREEN} />
        </g>
        {/* Sparkle knockout (sits on the disc) */}
        <g opacity={sparkle.opacity} transform={around(CX, CY, sparkle)}>
          <path d={SPARKLE_D} fill={KNOCKOUT} />
        </g>
        {/* Ring */}
        <g opacity={ring.opacity} transform={around(CX, CY, ring)}>
          <path fillRule="evenodd" clipRule="evenodd" d={RING_D} fill={GREEN} />
        </g>
      </svg>

      <div
        style={{
          fontWeight: 700,
          fontSize: size * 0.205,
          letterSpacing: '-0.02em',
          color: '#ffffff',
          opacity: wordP,
          transform: `translateY(${lerp(20, 0, wordP)}px)`,
          whiteSpace: 'nowrap',
          lineHeight: 1,
        }}
      >
        pdftoreel<span style={{ color: GREEN }}>.com</span>
      </div>
    </div>
  );
}
