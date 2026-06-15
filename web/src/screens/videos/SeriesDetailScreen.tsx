import { useNavigate, useParams } from 'react-router-dom';
import { useSeriesStatus } from '@/hooks/queries';
import { seriesHeaderTitle, reelCardTitle, reelCardSubtitle } from '@/lib/videoLabels';
import { MediaCard } from '@/components/videos/MediaCard';
import { MediaGrid } from '@/components/videos/MediaGrid';
import { BackButton } from '@/components/ui/BackButton';
import { Spinner } from '@/components/ui/Spinner';

// Port of the reels-grid view in videos_screen (selectedSeries != null). Polls
// the single series every 5s while it's unfinished.
export default function SeriesDetailScreen() {
  const navigate = useNavigate();
  const { seriesId } = useParams();
  const id = Number(seriesId);
  const { data: series, isLoading } = useSeriesStatus(Number.isFinite(id) ? id : null);

  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <BackButton onClick={() => navigate('/videos')} />
      </div>
      <div className="px-5 pb-4">
        <h1 className="mt-2 text-2xl font-bold text-textPrimary">
          {/* While the series loads, render a placeholder rather than the
              "All reels" fallback so the wrong title never flashes. */}
          {series ? seriesHeaderTitle(series) : ' '}
        </h1>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto pb-6">
        {series ? (
          // Keep showing cached reels even if a background poll fails.
          <MediaGrid>
            {series.reels.map((reel) => {
              const done = reel.status === 'done';
              return (
                <button
                  key={reel.id}
                  type="button"
                  disabled={!done}
                  onClick={() => done && navigate(`/videos/${series.id}/${reel.id}`)}
                  className="group block w-full"
                  style={{ aspectRatio: '0.6', cursor: done ? 'pointer' : 'default' }}
                >
                  <MediaCard
                    thumbnailUrl={reel.thumbnailUrl}
                    title={reelCardTitle(reel)}
                    subtitle={reelCardSubtitle(reel)}
                    status={reel.status}
                    titleFontSize={14}
                  />
                </button>
              );
            })}
          </MediaGrid>
        ) : isLoading ? (
          <div className="flex h-full items-center justify-center">
            <Spinner size={50} />
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-error">
            Error loading reels
          </div>
        )}
      </div>
    </div>
  );
}
