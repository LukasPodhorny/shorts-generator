import { useUiStore } from '@/store/uiStore';
import { FileChip, LinkChip } from '@/components/ui/SourceChip';

// Horizontal strip of uploaded-file + source-link chips shown above the prompt
// field. Renders nothing when there are no attachments.
export function PromptChipStrip() {
  const uploadedFileKeys = useUiStore((s) => s.uploadedFileKeys);
  const sourceLinks = useUiStore((s) => s.sourceLinks);
  const removeUploadedFileKeyAt = useUiStore((s) => s.removeUploadedFileKeyAt);
  const removeSourceLink = useUiStore((s) => s.removeSourceLink);

  if (uploadedFileKeys.length === 0 && sourceLinks.length === 0) return null;

  return (
    <div className="mb-2.5 flex h-[60px] items-center overflow-x-auto">
      {uploadedFileKeys.map((key, i) => (
        <FileChip key={`f-${i}-${key}`} fileKey={key} onRemove={() => removeUploadedFileKeyAt(i)} />
      ))}
      {sourceLinks.map((url) => (
        <LinkChip key={`l-${url}`} url={url} onRemove={() => removeSourceLink(url)} />
      ))}
    </div>
  );
}
