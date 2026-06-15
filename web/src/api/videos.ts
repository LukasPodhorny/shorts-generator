import { api } from '@/lib/apiClient';
import {
  parseAvatar,
  parseVideoSeries,
  parseVideoTemplate,
  type Avatar,
  type VideoSeries,
  type VideoTemplate,
} from '@/types/models';

// Ports lib/services/video_service.dart. Endpoints + request/response shapes
// match the FastAPI backend exactly.

export async function listSeries(params: {
  limit?: number;
  offset?: number;
}): Promise<VideoSeries[]> {
  const { data } = await api.get('/api/series', { params });
  return (data as Record<string, unknown>[]).map(parseVideoSeries);
}

export async function getSeriesStatus(seriesId: number): Promise<VideoSeries> {
  const { data } = await api.get(`/api/status/${seriesId}`);
  return parseVideoSeries(data as Record<string, unknown>);
}

export interface StartGenerationArgs {
  templateName: string;
  avatarNames: string[];
  amount?: number;
  inputText?: string;
  files?: string[];
  links?: string[];
  enabledTags?: string[] | null;
}

export async function startGeneration(args: StartGenerationArgs): Promise<number> {
  const body: Record<string, unknown> = {
    template_name: args.templateName,
    avatar_names: args.avatarNames,
    amount: args.amount ?? 1,
    input_text: args.inputText,
    files: args.files,
  };
  if (args.links && args.links.length > 0) body.links = args.links;
  if (args.enabledTags != null) body.enabled_tags = args.enabledTags;

  const { data } = await api.post('/api/generate', body);
  return (data as { series_id: number }).series_id;
}

export async function uploadFile(file: File): Promise<string> {
  const form = new FormData();
  form.append('file', file, file.name);
  const { data } = await api.post('/api/upload/', form);
  return (data as { key: string }).key;
}

export async function listTemplates(): Promise<VideoTemplate[]> {
  const { data } = await api.get('/api/public/video-templates');
  return (data as Record<string, unknown>[]).map(parseVideoTemplate);
}

export async function listAvatars(): Promise<Avatar[]> {
  const { data } = await api.get('/api/public/avatars');
  return (data as Record<string, unknown>[]).map(parseAvatar);
}
