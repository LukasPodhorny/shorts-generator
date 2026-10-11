import { useRef, useState, type ReactNode, type RefObject } from 'react';
import { useUiStore } from '@/store/uiStore';
import { usePlanGeneration } from '@/hooks/usePlanGeneration';
import { UPLOAD_ACCEPT } from '@/lib/sourceFiles';
import { AttachFileIcon, GlobeIcon, PlusIcon, ArrowUpIcon } from '@/components/ui/icons';
import { Spinner } from '@/components/ui/Spinner';
import { AddLinkDialog } from '@/components/ui/AddLinkDialog';
import { PromptChipStrip } from '@/components/generate/PromptChipStrip';
import { PromptTextarea } from '@/components/generate/PromptTextarea';
import { TemplateStackButton } from './TemplateStackButton';
import { AvatarStackButton } from './AvatarStackButton';
import { TemplatePickerModal } from './TemplatePickerModal';
import { AvatarPickerModal } from './AvatarPickerModal';

function AttachMenuRow({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full cursor-pointer items-center gap-2.5 rounded-[10px] px-2.5 py-[9px] text-left text-textPrimary hover:bg-surface3"
    >
      {icon}
      <span className="text-sm font-medium">{label}</span>
    </button>
  );
}

// The chat composer: attachment chips, an auto-growing prompt field, and an
// action row with the attach (+) menu, optional template/avatar/reel-count
// controls, and the send button. Everything except the message is optional --
// the backend parser fills whatever is left blank.
export function ChatComposer({
  inputRef,
}: {
  inputRef?: RefObject<HTMLTextAreaElement | null>;
}) {
  const promptText = useUiStore((s) => s.promptText);
  const setPromptText = useUiStore((s) => s.setPromptText);
  const addSourceLink = useUiStore((s) => s.addSourceLink);
  const fileCount = useUiStore((s) => s.uploadedFileKeys.length);
  const linkCount = useUiStore((s) => s.sourceLinks.length);

  const { isUploading, isSubmitting, pickAndUploadFile, tryAddLink, submit } =
    usePlanGeneration();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const localTextareaRef = useRef<HTMLTextAreaElement>(null);
  const textareaRef = inputRef ?? localTextareaRef;
  const [menuOpen, setMenuOpen] = useState(false);
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [avatarOpen, setAvatarOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hovered, setHovered] = useState(false);

  const highlighted = hovered || focused || menuOpen;
  const canSend = promptText.trim() !== '' || fileCount > 0 || linkCount > 0;
  const busy = isUploading || isSubmitting;

  const closeMenu = () => {
    setMenuOpen(false);
    setHovered(false);
  };

  const onAddLinkClick = () => {
    closeMenu();
    if (tryAddLink()) setLinkDialogOpen(true);
  };

  const send = () => {
    if (busy || !canSend) return;
    void submit();
  };

  return (
    <div className="w-full">
      <div
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onMouseDown={(e) => {
          const t = e.target as HTMLElement;
          if (t === textareaRef.current || t.closest('button')) return;
          e.preventDefault();
          textareaRef.current?.focus();
        }}
        className="cursor-text rounded-[30px] bg-surface1 p-4 transition-colors"
        style={{
          border: `0.25px solid ${highlighted ? 'rgba(255,255,255,0.09)' : 'rgba(255,255,255,0.04)'}`,
        }}
      >
        <PromptChipStrip />

        <PromptTextarea
          textareaRef={textareaRef}
          value={promptText}
          onChange={setPromptText}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          maxLines={8}
          placeholder="Describe the reels you want to make..."
        />

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {/* Attach (+) button + menu */}
          <div className="relative z-20">
            <button
              type="button"
              disabled={isUploading}
              onClick={() => setMenuOpen((o) => !o)}
              className={`relative z-20 flex h-9 w-9 cursor-pointer items-center justify-center rounded-full text-textPrimary hover:bg-surface2 ${
                menuOpen ? 'bg-surface2' : ''
              }`}
              title="Add files or links"
            >
              {isUploading ? (
                <Spinner size={20} strokeWidth={2} />
              ) : (
                <PlusIcon
                  size={22}
                  style={{
                    transition: 'transform 200ms',
                    transform: menuOpen ? 'rotate(45deg)' : undefined,
                  }}
                />
              )}
            </button>

            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10 cursor-default" onClick={closeMenu} />
                <div className="absolute bottom-11 left-0 z-30 w-[232px] cursor-default rounded-2xl border border-white/[0.08] bg-surface2 p-1.5 shadow-[0_8px_20px_rgba(0,0,0,0.4)]">
                  <AttachMenuRow
                    icon={<AttachFileIcon size={18} />}
                    label="Add files or photos"
                    onClick={() => {
                      closeMenu();
                      fileInputRef.current?.click();
                    }}
                  />
                  <AttachMenuRow
                    icon={<GlobeIcon size={18} />}
                    label="Add link"
                    onClick={onAddLinkClick}
                  />
                </div>
              </>
            )}
          </div>

          <TemplateStackButton onClick={() => setTemplateOpen(true)} />
          <AvatarStackButton onClick={() => setAvatarOpen(true)} />

          <div className="ml-auto flex items-center">
            <button
              type="button"
              onClick={send}
              disabled={busy || !canSend}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-neon text-surface1 transition-opacity"
              style={{ opacity: busy || !canSend ? 0.4 : 1 }}
              title="Generate"
            >
              {isSubmitting ? (
                <Spinner size={20} strokeWidth={2} className="text-surface1" />
              ) : (
                <ArrowUpIcon size={22} />
              )}
            </button>
          </div>
        </div>
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
      <TemplatePickerModal open={templateOpen} onClose={() => setTemplateOpen(false)} />
      <AvatarPickerModal open={avatarOpen} onClose={() => setAvatarOpen(false)} />
    </div>
  );
}
