import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSeriesList } from '@/hooks/queries';
import { useScrollRestoration } from '@/hooks/useScrollRestoration';
import { seriesCardTitle, seriesCardSubtitle } from '@/lib/videoLabels';
import { MediaCard } from '@/components/videos/MediaCard';
import { MediaGrid } from '@/components/videos/MediaGrid';
import { Skeleton } from '@/components/ui/Skeleton';
import { ActionButton } from '@/components/ui/ActionButton';

function EmptyState({ onGenerate }: { onGenerate: () => void }) {
  return (
    <div className="flex h-full items-center justify-center px-5">
      <div className="flex w-full max-w-[420px] flex-col items-center text-center">
        <div className="flex h-[74px] w-[74px] items-center justify-center rounded-[20px] bg-surface2 text-textPrimary">
          <svg width="38" height="38" viewBox="0 0 24 24" fill="currentColor">
            <path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4zm14.5-1.5 4 2.5-4 2.5z" />
          </svg>
        </div>
        <h2 className="mt-4 text-[22px] font-bold text-textPrimary">No reels yet</h2>
        <p className="mt-2 text-sm leading-snug text-textSecondary">
          Create your first video in Generate mode and it will appear here.
        </p>
        <div className="mt-5 w-full">
          <ActionButton
            text="Generate your first reel"
            backgroundColor="transparent"
            textColor="var(--color-textPrimary)"
            borderColor="var(--color-textSecondary)"
            onClick={onGenerate}
          />
        </div>
      </div>
    </div>
  );
}

// A single reel-shaped (0.6 aspect) shimmer placeholder, used both for the
// initial load and for the trailing "loading more" cards during pagination.
function SkeletonCard() {
  return (
    <div className="w-full" style={{ aspectRatio: '0.6' }}>
      <Skeleton className="h-full w-full rounded-[30px]" />
    </div>
  );
}

// Port of the series list in videos_screen: paginated, polled grid of series.
export default function VideosScreen() {
  const navigate = useNavigate();
  const { data, isLoading, isError, error, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useSeriesList(true);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const scroll = useScrollRestoration<HTMLDivElement>('videos-list');

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) {
          void fetchNextPage();
        }
      },
      // Prefetch the next page ~800px before the sentinel scrolls into view so
      // the grid keeps growing ahead of the user instead of stalling on a
      // loader at the very bottom. Root is the overflow-y-auto scroll container
      // (the sentinel's DOM parent), not the viewport.
      { root: el.parentElement, rootMargin: '800px 0px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const series = data?.pages.flat() ?? [];

  return (
    <div className="flex h-full flex-col">
      {/* Spacer mirrors the back-button row in SeriesDetailScreen so the
          "All reels" title sits at the same Y as a series title. */}
      <div className="px-3 pt-3">
        <div className="h-10" />
      </div>
      <div className="px-5 pb-4">
        <h1 className="mt-2 text-2xl font-bold text-textPrimary">All reels</h1>
      </div>
      <div ref={scroll.ref} onScroll={scroll.onScroll} className="min-h-0 flex-1 overflow-y-auto pb-6">
        {series.length > 0 ? (
          // Keep showing cached reels even if a background poll fails — a
          // transient 500 shouldn't wipe the grid.
          <>
            <MediaGrid>
              {series.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => navigate(`/videos/${s.id}`)}
                  className="group block w-full cursor-pointer"
                  style={{ aspectRatio: '0.6' }}
                >
                  <MediaCard
                    thumbnailUrl={s.thumbnailUrl}
                    title={seriesCardTitle(s)}
                    subtitle={seriesCardSubtitle(s)}
                    status={s.status}
                  />
                </button>
              ))}
              {/* Trailing placeholders flow into the same grid while the next
                  page loads, matching the initial-load skeletons. */}
              {isFetchingNextPage &&
                Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={`next-${i}`} />)}
            </MediaGrid>
            <div ref={sentinelRef} className="h-px" />
          </>
        ) : isLoading ? (
          <MediaGrid>
            {Array.from({ length: 12 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </MediaGrid>
        ) : isError ? (
          <div className="flex h-full items-center justify-center text-error">
            Error loading reels: {String(error)}
          </div>
        ) : (
          <EmptyState onGenerate={() => navigate('/')} />
        )}
      </div>
    </div>
  );
}
