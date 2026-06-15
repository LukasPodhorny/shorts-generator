import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryClient';
import type { JobStatus, VideoSeries } from '@/types/models';

// DEV-ONLY: seeds the series query with mock data so the videos grid can be
// visually verified without an auth session, then renders nested routes.
const TITLES = [
  'Is Claude Fable the New Standard?',
  'A surreal bedtime parable where a father reads',
  'Claude Fable 5 AI Model Launch',
  "Jeff Bezos and Elon Musk's rivalry over space",
  'Worst IT Project Ideas You Should Avoid Using',
  'The hidden cost of technical debt explained',
  'Why your startup needs a design system',
  'A deep dive into transformer architectures',
  'Bitcoin and the future of decentralized money',
  'How to talk to AI like a senior engineer',
  'The art of the perfect commit message',
];

function mock(): VideoSeries[] {
  // < page size (10) so the infinite query treats it as the last page.
  return TITLES.slice(0, 9).map((topic, i) => {
    const failed = i === 4;
    return {
      id: i + 1,
      userId: 'preview',
      createdAt: new Date().toISOString(),
      status: 'done' as JobStatus,
      topic: failed ? null : topic,
      thumbnailUrl: failed ? null : `https://picsum.photos/seed/reel${i}/360/600`,
      reels: [
        {
          id: 100 + i,
          sequenceNumber: 1,
          status: 'done' as JobStatus,
          cloudflareR2Url: 'https://example.com/v.mp4',
          localPath: null,
          title: topic,
          description: null,
          thumbnailUrl: `https://picsum.photos/seed/reel${i}/360/600`,
          duration: '2:05',
        },
      ],
    };
  });
}

export default function SeedSeriesLayout() {
  const qc = useQueryClient();
  useState(() => {
    const data = mock();
    qc.setQueryData(queryKeys.series, { pages: [data], pageParams: [0] });
    data.forEach((s) => qc.setQueryData(queryKeys.seriesStatus(s.id), s));
    return null;
  });
  return <Outlet />;
}
