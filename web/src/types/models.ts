// Domain models + JSON parsers ported from lib/models/reel_models.dart.
// Response shapes match the FastAPI backend (shorts-generator/api).

export type JobStatus = 'queued' | 'processing' | 'done' | 'failed';

export function parseJobStatus(status: string): JobStatus {
  switch (status.toLowerCase()) {
    case 'queued':
      return 'queued';
    case 'processing':
      return 'processing';
    case 'done':
      return 'done';
    case 'failed':
      return 'failed';
    default:
      return 'failed';
  }
}

export interface Reel {
  id: number;
  sequenceNumber: number;
  status: JobStatus;
  cloudflareR2Url: string | null;
  localPath: string | null;
  title: string | null;
  description: string | null;
  thumbnailUrl: string | null;
  duration: string | null;
}

export function parseReel(json: Record<string, unknown>): Reel {
  return {
    id: json.id as number,
    sequenceNumber: json.sequence_number as number,
    status: parseJobStatus(json.status as string),
    cloudflareR2Url: (json.cloudflare_r2_url as string) ?? null,
    localPath: (json.local_path as string) ?? null,
    title: (json.title as string) ?? null,
    description: (json.description as string) ?? null,
    thumbnailUrl: (json.thumbnail_url as string) ?? null,
    duration: (json.duration as string) ?? null,
  };
}

export interface VideoSeries {
  id: number;
  userId: string;
  createdAt: string; // ISO 8601
  status: JobStatus;
  topic: string | null;
  thumbnailUrl: string | null;
  reels: Reel[];
}

export function parseVideoSeries(json: Record<string, unknown>): VideoSeries {
  return {
    id: json.id as number,
    userId: json.user_id as string,
    createdAt: json.created_at as string,
    status: parseJobStatus(json.status as string),
    topic: (json.topic as string) ?? null,
    thumbnailUrl: (json.thumbnail_url as string) ?? null,
    reels: ((json.reels as Record<string, unknown>[]) ?? []).map(parseReel),
  };
}

export function seriesDisplayTitle(s: VideoSeries): string {
  return s.topic ?? `Generation #${s.id}`;
}

export function seriesFirstVideoUrl(s: VideoSeries): string | null {
  for (const reel of s.reels) {
    if (reel.cloudflareR2Url) return reel.cloudflareR2Url;
  }
  return null;
}

export interface UserProfile {
  id: string;
  email: string | null;
  credits: number;
}

export function parseUserProfile(json: Record<string, unknown>): UserProfile {
  return {
    id: json.id as string,
    email: (json.email as string) ?? null,
    credits: json.credits as number,
  };
}

export interface TemplateTag {
  assetType: string;
  defaultEnabled: boolean;
}

export interface VideoTemplate {
  id: number;
  name: string;
  credits: number;
  previewUrl: string;
  thumbnailUrl: string | null;
  tags: TemplateTag[];
}

export function parseVideoTemplate(json: Record<string, unknown>): VideoTemplate {
  const rawTags = (json.tags as Record<string, unknown>[]) ?? [];
  return {
    id: json.id as number,
    name: json.name as string,
    credits: (json.credits as number) ?? 1,
    previewUrl: (json.preview_url as string) ?? '',
    thumbnailUrl: (json.thumbnail_url as string) ?? null,
    tags: rawTags.map((t) => ({
      assetType: t.asset_type as string,
      defaultEnabled: (t.default as boolean) ?? true,
    })),
  };
}

export interface Avatar {
  id: number;
  name: string;
  data: Record<string, unknown>;
}

export function parseAvatar(json: Record<string, unknown>): Avatar {
  return {
    id: json.id as number,
    name: json.name as string,
    data: (json.data as Record<string, unknown>) ?? {},
  };
}

// `face`/`preview_face_url` may be a plain string or a `{ url }` object.
function faceFieldUrl(field: unknown): string | null {
  if (field && typeof field === 'object' && 'url' in field) {
    return (field as { url: string }).url ?? null;
  }
  return (field as string) ?? null;
}

export function avatarFaceUrl(a: Avatar): string | null {
  return faceFieldUrl(a.data.face_url);
}

export function avatarStaticFaceUrl(a: Avatar): string | null {
  return faceFieldUrl(a.data.preview_face_url);
}

export function avatarDisplayName(a: Avatar): string {
  const name = a.data.name;
  return typeof name === 'string' && name.length > 0 ? name : a.name;
}
