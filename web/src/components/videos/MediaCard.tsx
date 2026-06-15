import type { JobStatus } from '@/types/models';
import { SafeImage } from '@/components/ui/SafeImage';
import { ErrorIcon } from '@/components/ui/icons';

const textShadow = '1px 1px 10px rgba(0,0,0,0.6)';

function TextOverlay({
  title,
  subtitle,
  titleFontSize,
  failed = false,
}: {
  title: string;
  subtitle: string;
  titleFontSize: number;
  failed?: boolean;
}) {
  return (
    <div className="absolute inset-0 flex flex-col justify-end p-3 text-left">
      <span
        className="font-bold leading-[1.1] text-white line-clamp-2"
        style={{ fontSize: titleFontSize, textShadow }}
      >
        {title}
      </span>
      {subtitle && (
        <span
          className="mt-1 text-xs"
          style={{ color: failed ? 'rgba(229,57,53,0.8)' : 'var(--color-textPrimary)', textShadow }}
        >
          {subtitle}
        </span>
      )}
    </div>
  );
}

// Bottom dark gradient under the text.
function BottomScrim() {
  return (
    <div
      className="absolute inset-0"
      style={{ background: 'linear-gradient(to bottom, transparent 50%, rgba(0,0,0,0.57))' }}
    />
  );
}

// Port of the videos_screen cell variants: done-with-thumbnail, generating
// (with/without thumbnail), and failed/missing placeholders.
export function MediaCard({
  thumbnailUrl,
  title,
  subtitle,
  status,
  titleFontSize = 16,
}: {
  thumbnailUrl: string | null;
  title: string;
  subtitle: string;
  status: JobStatus;
  titleFontSize?: number;
}) {
  const hasThumbnail = !!thumbnailUrl;
  const generating = status !== 'done' && status !== 'failed';
  const failed = status === 'failed';

  return (
    <div className="relative h-full w-full overflow-hidden rounded-[30px]">
      {failed ? (
        <div className="absolute inset-0 flex items-center justify-center" style={{ backgroundColor: '#412222' }}>
          <ErrorIcon size={48} style={{ color: 'rgba(244,67,54,0.7)' }} />
        </div>
      ) : generating && !hasThumbnail ? (
        <div className="generating-gradient absolute inset-0" />
      ) : generating && hasThumbnail ? (
        <>
          <SafeImage url={thumbnailUrl!} className="absolute inset-0 h-full w-full" />
          <div className="generating-gradient absolute inset-0 opacity-40" />
        </>
      ) : !hasThumbnail ? (
        <div className="absolute inset-0 flex items-center justify-center bg-surface2 text-textSecondary">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
            <path d="M21 5v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2m-2 0H5v9.5l3.5-3.5 2.5 2.5L14.5 9 19 13.5z" />
          </svg>
        </div>
      ) : (
        <SafeImage url={thumbnailUrl!} className="absolute inset-0 h-full w-full" />
      )}

      <BottomScrim />
      {/* Lighten the reel on hover (matches the desktop reel hover state). */}
      <div
        className="pointer-events-none absolute inset-0 bg-white/5 opacity-0  group-hover:opacity-100"
      />
      <TextOverlay title={title} subtitle={subtitle} titleFontSize={titleFontSize} failed={failed} />
    </div>
  );
}
