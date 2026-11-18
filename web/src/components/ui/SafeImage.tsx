import { useState } from 'react';

// Port of SafeNetworkImage: shows a shimmer while loading and a broken-image
// fallback on error.
export function SafeImage({
  url,
  className = '',
  alt = '',
  preserveLandscape = false,
}: {
  url: string;
  className?: string;
  alt?: string;
  preserveLandscape?: boolean;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const [landscape, setLandscape] = useState(false);

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
        onLoad={(event) => {
          setLoaded(true);
          setLandscape(event.currentTarget.naturalWidth > event.currentTarget.naturalHeight);
        }}
        onError={() => setError(true)}
        className="h-full w-full"
        style={{ opacity: loaded ? 1 : 0, objectFit: preserveLandscape && landscape ? 'contain' : 'cover' }}
      />
    </div>
  );
}
