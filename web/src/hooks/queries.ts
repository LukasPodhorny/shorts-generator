import {
  useInfiniteQuery,
  useQuery,
  type InfiniteData,
} from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryClient';
import { getMe } from '@/api/users';
import {
  getSeriesStatus,
  listAvatars,
  listSeries,
  listTemplates,
} from '@/api/videos';
import { useAuth } from '@/auth/AuthProvider';
import type { VideoSeries } from '@/types/models';

const SERIES_PAGE_SIZE = 10;

export function useUserProfile() {
  const { user } = useAuth();
  return useQuery({
    queryKey: queryKeys.userProfile,
    queryFn: getMe,
    enabled: !!user,
  });
}

// These load once on the generate screen, so a transient upstream/proxy blip
// (e.g. a 502 from a dropped socket) otherwise sticks until a manual refresh.
// Retry harder with backoff so they self-heal.
const RESILIENT_RETRY = 5;

export function useTemplates() {
  return useQuery({
    queryKey: queryKeys.templates,
    queryFn: listTemplates,
    retry: RESILIENT_RETRY,
  });
}

export function useAvatars() {
  return useQuery({
    queryKey: queryKeys.avatars,
    queryFn: listAvatars,
    retry: RESILIENT_RETRY,
  });
}

/**
 * Paginated series list (replaces SeriesListNotifier). Pages of 10; a short
 * page signals the end. Polls every 5s while any series/reel is unfinished —
 * matching the Flutter videos_screen 5s Timer.periodic.
 */
export function useSeriesList(pollingEnabled: boolean) {
  return useInfiniteQuery({
    queryKey: queryKeys.series,
    queryFn: ({ pageParam }) =>
      listSeries({ limit: SERIES_PAGE_SIZE, offset: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) =>
      lastPage.length < SERIES_PAGE_SIZE
        ? undefined
        : allPages.reduce((n, p) => n + p.length, 0),
    refetchInterval: (query) => {
      if (!pollingEnabled) return false;
      const data = query.state.data as
        | InfiniteData<VideoSeries[]>
        | undefined;
      const anyUnfinished = data?.pages.some((page) =>
        page.some(
          (s) =>
            s.status !== 'done' || s.reels.some((r) => r.status !== 'done'),
        ),
      );
      return anyUnfinished ? 5000 : false;
    },
  });
}

/** Single-series status poll (used by the detail view), 5s while unfinished. */
export function useSeriesStatus(seriesId: number | null) {
  return useQuery({
    queryKey: seriesId ? queryKeys.seriesStatus(seriesId) : ['seriesStatus', 'none'],
    queryFn: () => getSeriesStatus(seriesId as number),
    enabled: seriesId != null,
    refetchInterval: (query) => {
      const s = query.state.data as VideoSeries | undefined;
      if (!s) return false;
      const unfinished =
        s.status !== 'done' || s.reels.some((r) => r.status !== 'done');
      return unfinished ? 5000 : false;
    },
  });
}
