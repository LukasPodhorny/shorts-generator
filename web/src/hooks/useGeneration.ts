import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { startGeneration, uploadFile } from '@/api/videos';
import { apiErrorMessage } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryClient';
import { MAX_SOURCE_LINKS, useUiStore } from '@/store/uiStore';
import { toast } from '@/store/toastStore';

// Encapsulates the upload + start-generation logic shared by the desktop
// PromptInputPanel and the mobile BottomInputArea (ports their identical
// _pickAndUploadFile / _startGeneration methods).
export function useGeneration() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  const pickAndUploadFile = useCallback(
    async (file: File) => {
      setIsUploading(true);
      try {
        const key = await uploadFile(file);
        useUiStore.getState().addUploadedFileKey(key);
      } catch (e) {
        toast(`Upload failed: ${apiErrorMessage(e)}`);
      } finally {
        setIsUploading(false);
      }
    },
    [],
  );

  const tryAddLink = useCallback((): boolean => {
    if (useUiStore.getState().sourceLinks.length >= MAX_SOURCE_LINKS) {
      toast('You can add up to 10 links');
      return false;
    }
    return true;
  }, []);

  const start = useCallback(async () => {
    const s = useUiStore.getState();
    const {
      selectedTemplateName: templateName,
      selectedTemplate: template,
      selectedAvatarNames,
      promptText: prompt,
      uploadedFileKeys: files,
      sourceLinks: links,
      reelCount,
      enabledTagsByTemplate,
    } = s;
    const avatarNames = [...selectedAvatarNames];

    const enabledTags =
      !template || template.tags.length === 0
        ? null
        : [
            ...(enabledTagsByTemplate[template.name] ??
              new Set(
                template.tags.filter((t) => t.defaultEnabled).map((t) => t.assetType),
              )),
          ];

    if (!templateName) {
      toast('Please select a template');
      return;
    }
    if (avatarNames.length === 0) {
      toast('Please select at least one avatar');
      return;
    }
    if (prompt.trim() === '' && files.length === 0 && links.length === 0) {
      toast('Add a prompt, file, or link first');
      return;
    }

    setIsGenerating(true);
    try {
      await startGeneration({
        templateName,
        avatarNames,
        amount: reelCount,
        inputText: prompt,
        files,
        links,
        enabledTags,
      });
      toast('Generation started! Check your reels.');
      s.resetGenerationInputs();
      await queryClient.invalidateQueries({ queryKey: queryKeys.series });
      navigate('/videos');
    } catch (e) {
      toast(`Failed to start generation: ${apiErrorMessage(e)}`);
    } finally {
      setIsGenerating(false);
    }
  }, [navigate, queryClient]);

  return { isUploading, isGenerating, pickAndUploadFile, tryAddLink, start };
}
