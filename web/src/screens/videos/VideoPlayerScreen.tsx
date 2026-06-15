import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useSeriesStatus } from '@/hooks/queries';
import { toast } from '@/store/toastStore';
import { Spinner } from '@/components/ui/Spinner';

function fmt(seconds: number): string {
  if (!Number.isFinite(seconds)) return '00:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function CloseIcon() {
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
    >
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

// Port of VideoPlayerScreen: a full-screen player with auto-hiding controls,
// scrubber, copy-link share, byte-blob download and fullscreen toggle.
export default function VideoPlayerScreen() {
  const navigate = useNavigate();
  const { seriesId, reelId } = useParams();
  const id = Number(seriesId);
  const { data: series, isLoading } = useSeriesStatus(Number.isFinite(id) ? id : null);
  const reel = series?.reels.find((r) => r.id === Number(reelId));
  const url = reel?.cloudflareR2Url ?? '';

  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [playing, setPlaying] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  // True until the video has buffered enough to play, and again whenever it
  // stalls — drives the centered loading spinner.
  const [buffering, setBuffering] = useState(true);

  const close = useCallback(() => navigate(-1), [navigate]);

  const startHideTimer = useCallback(() => {
    if (hideTimer.current) clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (videoRef.current && !videoRef.current.paused) setShowControls(false);
    }, 3000);
  }, []);

  const nudgeControls = useCallback(() => {
    setShowControls(true);
    startHideTimer();
  }, [startHideTimer]);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
    nudgeControls();
  }, [nudgeControls]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      else if (e.key === ' ') {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [close, togglePlay]);

  useEffect(() => {
    const onFs = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  const share = async () => {
    if (!url) return;
    await navigator.clipboard.writeText(url);
    toast('Link copied to clipboard');
  };

  const download = async () => {
    if (!url) return;
    setDownloading(true);
    try {
      const res = await fetch(url);
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = `reel_${reel?.id}_${Date.now()}.mp4`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      toast('Video downloaded successfully!');
    } catch (e) {
      toast(`Failed to download: ${e instanceof Error ? e.message : e}`);
    } finally {
      setDownloading(false);
    }
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void containerRef.current?.requestFullscreen();
  };

  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-black">
        <Spinner size={50} />
      </div>
    );
  }

  if (!url) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-black text-white">
        <p>No video available</p>
        <button type="button" onClick={close} className="rounded-full bg-white/10 px-4 py-2">
          Close
        </button>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full bg-black"
      onMouseMove={nudgeControls}
      style={{ cursor: showControls ? 'default' : 'none' }}
    >
      <video
        ref={videoRef}
        src={url}
        autoPlay
        playsInline
        className="absolute inset-0 h-full w-full object-contain"
        onClick={togglePlay}
        onPlay={() => {
          setPlaying(true);
          startHideTimer();
        }}
        onPause={() => setPlaying(false)}
        onLoadStart={() => setBuffering(true)}
        onWaiting={() => setBuffering(true)}
        onPlaying={() => setBuffering(false)}
        onCanPlay={() => setBuffering(false)}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
      />

      {/* Buffering spinner (always visible while loading, even with controls
          hidden). */}
      {buffering && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <Spinner size={56} strokeWidth={3} style={{ color: '#fff' }} />
        </div>
      )}

      {/* Controls overlay */}
      <div
        className="absolute inset-0 transition-opacity duration-200"
        style={{
          opacity: showControls ? 1 : 0,
          pointerEvents: showControls ? 'auto' : 'none',
          background:
            'linear-gradient(to bottom, rgba(0,0,0,0.54) 0%, transparent 40%, rgba(0,0,0,0.87) 90%)',
        }}
      >
        {/* Top bar */}
        <div className="flex items-center justify-between p-3">
          <button
            type="button"
            onClick={close}
            className="flex h-11 w-11 items-center justify-center rounded-full text-white hover:bg-white/15"
            aria-label="Close"
          >
            <CloseIcon />
          </button>
          <div className="flex items-center gap-1 text-white">
            <button
              type="button"
              onClick={share}
              className="flex h-11 w-11 items-center justify-center rounded-full  hover:bg-white/15"
              aria-label="Copy link"
            >
              <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
                <path d="M3.9 12a3.1 3.1 0 0 1 3.1-3.1h4V7H7a5 5 0 0 0 0 10h4v-1.9H7A3.1 3.1 0 0 1 3.9 12M8 13h8v-2H8zm9-6h-4v1.9h4a3.1 3.1 0 0 1 0 6.2h-4V17h4a5 5 0 0 0 0-10" />
              </svg>
            </button>
            <button
              type="button"
              onClick={download}
              disabled={downloading}
              className="flex h-11 w-11 items-center justify-center rounded-full  hover:bg-white/15 disabled:hover:bg-transparent"
              aria-label="Download"
            >
              {downloading ? (
                <Spinner size={24} strokeWidth={2} style={{ color: 'var(--color-neon)' }} />
              ) : (
                <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M5 20h14v-2H5zm7-3 5-5h-3V4h-4v8H7z" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Center play/pause (hidden while the buffering spinner shows) */}
        {!buffering && (
        <button
          type="button"
          onClick={togglePlay}
          className="absolute left-1/2 top-1/2 flex h-20 w-20 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-white bg-black/30 text-white hover:bg-white/15"
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? (
            <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6.5" y="5" width="3.6" height="14" rx="1.8" />
              <rect x="13.9" y="5" width="3.6" height="14" rx="1.8" />
            </svg>
          ) : (
            <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 6.82v10.36c0 .79.87 1.27 1.54.84l8.15-5.18a1 1 0 0 0 0-1.69L9.54 5.98A1 1 0 0 0 8 6.82z" />
            </svg>
          )}
        </button>
        )}

        {/* Bottom scrubber */}
        <div className="absolute inset-x-0 bottom-0 px-4 pb-5 pt-2">
          <input
            type="range"
            min={0}
            max={duration || 1}
            step={0.1}
            value={current}
            onChange={(e) => {
              const t = Number(e.target.value);
              if (videoRef.current) videoRef.current.currentTime = t;
              setCurrent(t);
            }}
            className="video-scrubber w-full"
            style={{ ['--progress' as string]: `${duration ? (current / duration) * 100 : 0}%` }}
          />
          <div className="mt-2 flex items-center justify-between pl-1 text-xs text-white">
            <span>{fmt(current)}</span>
            <div className="flex items-center gap-1">
              <span>{fmt(duration)}</span>
              <button
                type="button"
                onClick={toggleFullscreen}
                className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-white/15"
                aria-label="Fullscreen"
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
                  {isFullscreen ? (
                    <path d="M5 16h3v3h2v-5H5zm3-8H5v2h5V5H8zm6 11h2v-3h3v-2h-5zm2-11V5h-2v5h5V8z" />
                  ) : (
                    <path d="M7 14H5v5h5v-2H7zm-2-4h2V7h3V5H5zm12 7h-3v2h5v-5h-2zM14 5v2h3v3h2V5z" />
                  )}
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
