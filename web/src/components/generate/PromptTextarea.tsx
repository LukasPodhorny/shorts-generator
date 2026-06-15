import { useEffect, useLayoutEffect, useRef, type Ref } from 'react';

// Auto-growing prompt field: grows from 1 line up to `maxLines`, then scrolls —
// matching the Flutter TextField(minLines: 1, maxLines: 3). Line height and
// padding are fixed so the grow math is exact.
const LINE_HEIGHT = 20; // px
const PAD_Y = 20; // pt-2 (8) + pb-3 (12)

export function PromptTextarea({
  value,
  onChange,
  onFocus,
  onBlur,
  placeholder,
  maxLines = 3,
  textareaRef,
}: {
  value: string;
  onChange: (v: string) => void;
  onFocus?: () => void;
  onBlur?: () => void;
  placeholder?: string;
  maxLines?: number;
  textareaRef?: Ref<HTMLTextAreaElement>;
}) {
  const innerRef = useRef<HTMLTextAreaElement>(null);
  const maxHeight = maxLines * LINE_HEIGHT + PAD_Y;

  const resize = () => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = `${Math.min(el.scrollHeight, maxHeight)}px`;
  };

  // Resize on value change (covers paste, clear, programmatic edits).
  useLayoutEffect(resize, [value]);

  // Expose the inner node through the optional forwarded ref.
  useEffect(() => {
    if (!textareaRef) return;
    if (typeof textareaRef === 'function') textareaRef(innerRef.current);
    else (textareaRef as { current: HTMLTextAreaElement | null }).current = innerRef.current;
  }, [textareaRef]);

  return (
    <textarea
      ref={innerRef}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={onFocus}
      onBlur={onBlur}
      rows={1}
      placeholder={placeholder}
      style={{ height: LINE_HEIGHT + PAD_Y, maxHeight, lineHeight: `${LINE_HEIGHT}px` }}
      className="block w-full resize-none overflow-y-auto bg-transparent px-2 pb-3 pt-2 text-sm font-medium text-textPrimary caret-textPrimary outline-none placeholder:font-medium placeholder:text-textSecondary"
    />
  );
}
