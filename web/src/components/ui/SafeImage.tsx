import { useState } from 'react';

// Port of SafeNetworkImage: shows a shimmer while loading and a broken-image
// fallback on error.
export function SafeImage({
  url,
  className = '',
  alt = '',
}: {
  url: string;
  className?: string;
  alt?: string;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  if (!url || error) {
    return (
      <div className={`flex items-center justify-center bg-neutral-800 ${className}`}>
        <span className="text-white/20">🖼</span>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden ${className}`}>
      {!loaded && <div className="absolute inset-0 animate-pulse bg-shimmerBase" />}
      <img
        src={url}
        alt={alt}
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
        className="h-full w-full object-cover"
        style={{ opacity: loaded ? 1 : 0 }}
      />
    </div>
  );
}
