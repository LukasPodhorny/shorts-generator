import { useRef, useState } from 'react';
import { useUiStore } from '@/store/uiStore';
import { useGeneration } from '@/hooks/useGeneration';
import { UPLOAD_ACCEPT } from '@/lib/sourceFiles';
import { AttachFileIcon, GlobeIcon, PlusIcon } from '@/components/ui/icons';
import { Spinner } from '@/components/ui/Spinner';
import { AddLinkDialog } from '@/components/ui/AddLinkDialog';
import { PromptChipStrip } from './PromptChipStrip';
import { PromptTextarea } from './PromptTextarea';
import { GenerateButton } from './GenerateButton';

function AttachMenuRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
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

// Ports the desktop PromptInputPanel: attachment chips, prompt field, the
// plus/attach menu and the generate button — inside a focus-highlighted card.
export function PromptInputPanel() {
  const promptText = useUiStore((s) => s.promptText);
  const setPromptText = useUiStore((s) => s.setPromptText);
  const addSourceLink = useUiStore((s) => s.addSourceLink);
  const { isUploading, isGenerating, pickAndUploadFile, tryAddLink, start } = useGeneration();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hovered, setHovered] = useState(false);

  const highlighted = hovered || focused || menuOpen;

  // Closing the menu also clears `hovered`: while the menu (or a dialog opened
  // from it) is up, the full-screen dismiss overlay sits inside the card, so the
  // card's onMouseLeave never fires and `hovered` would otherwise stay stuck on.
  const closeMenu = () => {
    setMenuOpen(false);
    setHovered(false);
  };

  const onAddLinkClick = () => {
    closeMenu();
    if (tryAddLink()) setLinkDialogOpen(true);
  };

  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[900px] px-12 pb-6">
        <div
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onMouseDown={(e) => {
            // Clicking empty card area focuses the prompt. Must NOT preventDefault
            // when the click lands on the textarea itself (that would block caret
            // placement and text selection) or on a button.
            const t = e.target as HTMLElement;
            if (t === textareaRef.current || t.closest('button')) return;
            e.preventDefault();
            textareaRef.current?.focus();
          }}
          className="cursor-text rounded-[30px] bg-surface1 p-4 transition-colors"
          style={{
            border: `0.25px solid ${highlighted ? 'rgba(255,255,255,0.09)' : 'transparent'}`,
          }}
        >
          <PromptChipStrip />

          <PromptTextarea
            textareaRef={textareaRef}
            value={promptText}
            onChange={setPromptText}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Input prompt..."
          />

          <div className="flex items-center">
            {/* Attach (plus) button + menu. z-20 keeps the button above the
                dismiss overlay so it stays highlighted + clickable while open. */}
            <div className="relative z-20">
              <button
                type="button"
                disabled={isUploading}
                onClick={() => setMenuOpen((o) => !o)}
                className={`relative z-20 flex h-11 w-11 cursor-pointer items-center justify-center rounded-full text-textPrimary hover:bg-surface2 ${menuOpen ? 'bg-surface2' : ''
                  }`}
              >
                {isUploading ? (
                  <Spinner size={24} strokeWidth={2} />
                ) : (
                  <PlusIcon
                    size={24}
                    style={{
                      transition: 'transform 200ms',
                      transform: menuOpen ? 'rotate(45deg)' : undefined,
                    }}
                  />
                )}
              </button>

              {menuOpen && (
                <>
                  {/* cursor-default stops the card's cursor-text from
                      inheriting onto the full-screen dismiss overlay. */}
                  <div
                    className="fixed inset-0 z-10 cursor-default"
                    onClick={closeMenu}
                  />
                  <div className="absolute bottom-12 left-0 z-30 w-[232px] cursor-default rounded-2xl border border-white/[0.08] bg-surface2 p-1.5 shadow-[0_8px_20px_rgba(0,0,0,0.4)]">
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

            <div className="flex-1" />
            <GenerateButton
              disabled={isUploading || isGenerating}
              generating={isGenerating}
              onClick={start}
            />
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
    </div>
  );
}
