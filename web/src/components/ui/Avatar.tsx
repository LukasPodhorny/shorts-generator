import { useState, useEffect, type ReactNode } from 'react';

// Renders a user avatar image with a graceful fallback. Google profile photos
// (lh3.googleusercontent.com) often 403/429 when a referrer is sent and stall
// or fail intermittently; without an onError handler the browser then paints
// its broken-image glyph, which clipped by `rounded-full` looks like a
// fragmented circle. `referrerPolicy="no-referrer"` avoids most of those
// failures, and the fallback covers the rest.
export function Avatar({
  src,
  fallback,
  className = '',
}: {
  src?: string | null;
  /** Shown when there is no src or the image fails to load. */
  fallback: ReactNode;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  // Reset the error state when the source changes (e.g. on login).
  useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src || failed) return <>{fallback}</>;

  return (
    <img
      src={src}
      alt=""
      className={className}
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}
