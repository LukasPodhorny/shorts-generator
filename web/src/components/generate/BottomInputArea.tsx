import { useRef, useState } from 'react';
import { useUiStore } from '@/store/uiStore';
import { useGeneration } from '@/hooks/useGeneration';
import { UPLOAD_ACCEPT } from '@/lib/sourceFiles';
import { LinkIcon, PlusIcon } from '@/components/ui/icons';
import { Spinner } from '@/components/ui/Spinner';
import { AddLinkDialog } from '@/components/ui/AddLinkDialog';
import { PromptChipStrip } from './PromptChipStrip';
import { PromptTextarea } from './PromptTextarea';
import { GenerateButton } from './GenerateButton';

// Ports the mobile BottomInputArea: a top-rounded bar fixed to the bottom with
// the prompt field, separate upload + link buttons, and the generate button.
export function BottomInputArea() {
  const promptText = useUiStore((s) => s.promptText);
  const setPromptText = useUiStore((s) => s.setPromptText);
  const addSourceLink = useUiStore((s) => s.addSourceLink);
  const { isUploading, isGenerating, pickAndUploadFile, tryAddLink, start } = useGeneration();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);

  return (
    <div className="rounded-t-[30px] bg-surface1 p-4 shadow-[0_-5px_10px_rgba(0,0,0,0.15)]">
      <PromptChipStrip />

      <PromptTextarea
        value={promptText}
        onChange={setPromptText}
        placeholder="Input prompt..."
      />

      <div className="flex items-center">
        <button
          type="button"
          disabled={isUploading}
          onClick={() => fileInputRef.current?.click()}
          className="flex h-11 w-11 items-center justify-center rounded-full text-textPrimary"
        >
          {isUploading ? <Spinner size={24} strokeWidth={2} /> : <PlusIcon size={24} />}
        </button>
        <button
          type="button"
          onClick={() => {
            if (tryAddLink()) setLinkDialogOpen(true);
          }}
          className="flex h-11 w-11 items-center justify-center rounded-full text-textPrimary"
        >
          <LinkIcon size={24} />
        </button>
        <div className="flex-1" />
        <GenerateButton
          disabled={isUploading || isGenerating}
          generating={isGenerating}
          onClick={start}
        />
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={UPLOAD_ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (file) void pickAndUploadFile(file);
        }}
      />
      <AddLinkDialog
        open={linkDialogOpen}
        onClose={() => setLinkDialogOpen(false)}
        onAdd={addSourceLink}
      />
    </div>
  );
}
