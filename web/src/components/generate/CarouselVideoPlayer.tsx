import { useEffect, useRef, useState } from 'react';

// Ports CarouselVideoPlayer: muted, looping preview video that plays only
// while its card is the centered/selected one. Falls back to the thumbnail
// image (then a shimmer) until the video can play.
export function CarouselVideoPlayer({
  videoUrl,
  thumbnailUrl,
  isSelected,
}: {
  videoUrl: string;
  thumbnailUrl: string;
  isSelected: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [canPlay, setCanPlay] = useState(false);
  const [errored, setErrored] = useState(!videoUrl.trim());

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !canPlay) return;
    if (isSelected) {
      void v.play().catch(() => {});
    } else {
      v.pause();
    }
  }, [isSelected, canPlay]);

  const showFallback = !canPlay || errored;

  return (
    <div className="absolute inset-0 overflow-hidden">
      {showFallback &&
        (thumbnailUrl.trim() ? (
          <img
            src={thumbnailUrl}
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            onError={() => setErrored(true)}
          />
        ) : (
          <div className="absolute inset-0 animate-pulse bg-shimmerBase" />
        ))}

      {!errored && (
        <video
          ref={videoRef}
          src={videoUrl}
          muted
          loop
          playsInline
          preload="metadata"
          onCanPlay={() => setCanPlay(true)}
          onError={() => setErrored(true)}
          className="absolute inset-0 h-full w-full object-cover"
          style={{ opacity: canPlay ? 1 : 0 }}
        />
      )}
    </div>
  );
}
