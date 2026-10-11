import { useRef } from 'react';
import { useAuth } from '@/auth/AuthProvider';
import { useUiStore } from '@/store/uiStore';
import { ChatComposer } from '@/components/generate/chat/ChatComposer';
import { SuggestionChips } from '@/components/generate/chat/SuggestionChips';

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

function firstName(displayName: string | null | undefined): string | null {
  if (!displayName) return null;
  return displayName.trim().split(/\s+/)[0] ?? null;
}

// The default generate experience: a centered chat-style landing. Type one
// message (optionally attach files/links and pick a template/avatars) and the
// backend figures out the rest via /api/plan. The classic carousel builder
// lives on the separate Studio tab.
export default function ChatGenerate() {
  const { user } = useAuth();
  const promptText = useUiStore((s) => s.promptText);
  const setPromptText = useUiStore((s) => s.setPromptText);
  const fileCount = useUiStore((s) => s.uploadedFileKeys.length);
  const linkCount = useUiStore((s) => s.sourceLinks.length);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const name = firstName(user?.displayName);
  const isEmpty = promptText.trim() === '' && fileCount === 0 && linkCount === 0;

  const pick = (prompt: string) => {
    setPromptText(prompt);
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (el) {
        el.focus();
        el.setSelectionRange(el.value.length, el.value.length);
      }
    });
  };

  return (
    <div className="h-full w-full overflow-y-auto bg-background">
      <div className="mx-auto flex min-h-full max-w-[760px] flex-col items-center justify-center px-4 py-12">
        {/* Only the composer is in the centering flow. The greeting and the
            suggestion chips float above/below it (absolute), so showing or
            hiding the chips never moves the input out of the center. */}
        <div className="relative w-full">
          <h1 className="absolute bottom-full left-0 right-0 mb-10 text-center text-3xl font-semibold tracking-tight text-textPrimary">
            {greeting()}
            {name ? `, ${name}` : ''}
          </h1>

          <ChatComposer inputRef={inputRef} />

          {isEmpty && (
            <div className="absolute left-0 right-0 top-full mt-6">
              <SuggestionChips onPick={pick} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
