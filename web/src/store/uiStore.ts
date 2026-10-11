import { create } from 'zustand';
import type { VideoTemplate } from '@/types/models';

// Local UI state ported from lib/ui_providers.dart. Server data (series,
// templates, avatars, profile) lives in TanStack Query, not here.

export const MAX_SELECTED_AVATARS = 4;
export const MAX_SOURCE_LINKS = 10;

interface UiState {
  // Generation selections
  reelCount: number; // 1..7
  selectedAvatarNames: Set<string>;
  selectedTemplateName: string | null;
  selectedTemplate: VideoTemplate | null;
  promptText: string;
  uploadedFileKeys: string[];
  sourceLinks: string[];
  // Per-template enabled tags: template.name -> set of enabled asset_type.
  enabledTagsByTemplate: Record<string, Set<string>>;
  // Chat (/plan) flow only: an explicit reel-count override. null means "let
  // the AI decide", so the parser fills `amount` itself. Kept separate from
  // reelCount (which the classic studio screen always sends as 1..7).
  amountOverride: number | null;

  setReelCount: (n: number) => void;
  setAmountOverride: (n: number | null) => void;
  toggleAvatar: (name: string) => boolean; // returns false if at max
  selectTemplate: (template: VideoTemplate) => void;
  clearTemplate: () => void;
  setPromptText: (text: string) => void;
  addUploadedFileKey: (key: string) => void;
  removeUploadedFileKeyAt: (index: number) => void;
  addSourceLink: (url: string) => void;
  removeSourceLink: (url: string) => void;
  setEnabledTags: (templateName: string, tags: Set<string>) => void;
  resetGenerationInputs: () => void;
  resetOnLogout: () => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  reelCount: 1,
  selectedAvatarNames: new Set(),
  selectedTemplateName: null,
  selectedTemplate: null,
  promptText: '',
  uploadedFileKeys: [],
  sourceLinks: [],
  enabledTagsByTemplate: {},
  amountOverride: null,

  setReelCount: (n) => set({ reelCount: Math.max(1, Math.min(7, n)) }),

  setAmountOverride: (n) =>
    set({ amountOverride: n == null ? null : Math.max(1, Math.min(7, n)) }),

  toggleAvatar: (name) => {
    const current = get().selectedAvatarNames;
    const next = new Set(current);
    if (next.has(name)) {
      next.delete(name);
    } else if (next.size >= MAX_SELECTED_AVATARS) {
      return false;
    } else {
      next.add(name);
    }
    set({ selectedAvatarNames: next });
    return true;
  },

  selectTemplate: (template) =>
    set({ selectedTemplate: template, selectedTemplateName: template.name }),

  clearTemplate: () => set({ selectedTemplate: null, selectedTemplateName: null }),

  setPromptText: (text) => set({ promptText: text }),

  addUploadedFileKey: (key) =>
    set((s) => ({ uploadedFileKeys: [...s.uploadedFileKeys, key] })),

  removeUploadedFileKeyAt: (index) =>
    set((s) => ({
      uploadedFileKeys: s.uploadedFileKeys.filter((_, i) => i !== index),
    })),

  addSourceLink: (url) =>
    set((s) =>
      s.sourceLinks.includes(url)
        ? s
        : { sourceLinks: [...s.sourceLinks, url] },
    ),

  removeSourceLink: (url) =>
    set((s) => ({ sourceLinks: s.sourceLinks.filter((l) => l !== url) })),

  setEnabledTags: (templateName, tags) =>
    set((s) => ({
      enabledTagsByTemplate: { ...s.enabledTagsByTemplate, [templateName]: tags },
    })),

  resetGenerationInputs: () =>
    set({ promptText: '', uploadedFileKeys: [], sourceLinks: [], amountOverride: null }),

  resetOnLogout: () =>
    set({
      selectedAvatarNames: new Set(),
      selectedTemplateName: null,
      selectedTemplate: null,
      promptText: '',
      uploadedFileKeys: [],
      sourceLinks: [],
      enabledTagsByTemplate: {},
      amountOverride: null,
    }),
}));
