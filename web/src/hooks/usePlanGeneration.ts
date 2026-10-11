import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { uploadFile } from '@/api/videos';
import { startPlan, type PlanAttachment } from '@/api/plan';
import { apiErrorMessage } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryClient';
import { MAX_SOURCE_LINKS, useUiStore } from '@/store/uiStore';
import { toast } from '@/store/toastStore';

// Submit logic for the chatbot (/api/plan) entry point. Mirrors useGeneration's
// upload/link helpers, but instead of POSTing a fully-specified GenerateRequest
// it sends the freeform instruction + attachments and lets the backend parser
// fill in whatever the user left unspecified. Any template/avatar/amount the
// user did pick is forwarded as a manual choice (which the parser must respect).
export function usePlanGeneration() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isUploading, setIsUploading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const pickAndUploadFile = useCallback(async (file: File) => {
    setIsUploading(true);
    try {
      const key = await uploadFile(file);
      useUiStore.getState().addUploadedFileKey(key);
    } catch (e) {
      toast(`Upload failed: ${apiErrorMessage(e)}`);
    } finally {
      setIsUploading(false);
    }
  }, []);

  const tryAddLink = useCallback((): boolean => {
    if (useUiStore.getState().sourceLinks.length >= MAX_SOURCE_LINKS) {
      toast('You can add up to 10 links');
      return false;
    }
    return true;
  }, []);

  const submit = useCallback(async () => {
    const s = useUiStore.getState();
    const {
      promptText,
      uploadedFileKeys,
      sourceLinks,
      selectedTemplateName,
      selectedTemplate: template,
      selectedAvatarNames,
      amountOverride,
      enabledTagsByTemplate,
    } = s;

    const instruction = promptText.trim();
    if (instruction === '' && uploadedFileKeys.length === 0 && sourceLinks.length === 0) {
      toast('Type a message, or add a file or link first');
      return;
    }

    const attachments: PlanAttachment[] = [
      ...uploadedFileKeys.map((key) => ({
        type: 'file' as const,
        name: key.split('/').pop() ?? key,
        key,
      })),
      ...sourceLinks.map((url) => ({ type: 'link' as const, url })),
    ];

    // enabled_tags only means something relative to a chosen template. When the
    // user left the template for the AI to pick, send null so the parser decides.
    const enabledTags =
      !template || template.tags.length === 0
        ? null
        : [
            ...(enabledTagsByTemplate[template.name] ??
              new Set(
                template.tags.filter((t) => t.defaultEnabled).map((t) => t.assetType),
              )),
          ];

    setIsSubmitting(true);
    try {
      await startPlan({
        instruction,
        attachments,
        templateName: selectedTemplateName,
        avatarNames: [...selectedAvatarNames],
        amount: amountOverride,
        enabledTags,
      });
      toast('Generation started! Check your reels.');
      s.resetGenerationInputs();
      await queryClient.invalidateQueries({ queryKey: queryKeys.series });
      navigate('/videos');
    } catch (e) {
      toast(`Failed to start generation: ${apiErrorMessage(e)}`);
    } finally {
      setIsSubmitting(false);
    }
  }, [navigate, queryClient]);

  return { isUploading, isSubmitting, pickAndUploadFile, tryAddLink, submit };
}
