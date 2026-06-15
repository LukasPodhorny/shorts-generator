import { useState } from 'react';

const EyeIcon = ({ off }: { off: boolean }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    {off ? (
      <path d="M12 7a5 5 0 0 1 5 5c0 .65-.13 1.26-.36 1.83l2.92 2.92A11.8 11.8 0 0 0 23 12c-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.15A5 5 0 0 1 12 7M2.4 3.4 1 4.8l2.5 2.5A11.8 11.8 0 0 0 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l3.42 3.42 1.41-1.41zM7.5 8.5l1.6 1.6A3 3 0 0 0 12 15c.34 0 .67-.06.98-.16l1.6 1.6A5 5 0 0 1 7 12c0-1.27.5-2.42 1.3-3.27z" />
    ) : (
      <path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5M12 17a5 5 0 1 1 0-10 5 5 0 0 1 0 10m0-8a3 3 0 1 0 0 6 3 3 0 0 0 0-6" />
    )}
  </svg>
);

// Port of MinimalistInputField: labelled input with a focus-driven neon border,
// optional password visibility toggle and error text.
export function InputField({
  label,
  hint,
  value,
  onChange,
  error,
  isPassword = false,
  type = 'text',
  autoFocus = false,
  onSubmit,
}: {
  label?: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  error?: string | null;
  isPassword?: boolean;
  type?: string;
  autoFocus?: boolean;
  onSubmit?: () => void;
}) {
  const [focused, setFocused] = useState(false);
  const [show, setShow] = useState(false);

  const borderColor = error
    ? 'var(--color-error)'
    : focused
      ? 'var(--color-neon)'
      : 'var(--color-surface3)';

  return (
    <div className="flex flex-col">
      {label && (
        <label className="mb-2 text-[13px] font-medium text-textPrimary">{label}</label>
      )}
      <div
        className="flex items-center rounded-xl bg-surface1 transition-colors"
        style={{ border: `1px solid ${borderColor}` }}
      >
        <input
          autoFocus={autoFocus}
          type={isPassword ? (show ? 'text' : 'password') : type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onSubmit?.();
          }}
          placeholder={hint}
          className="w-full bg-transparent px-4 py-4 text-base text-textPrimary caret-neon outline-none placeholder:text-textSecondary"
        />
        {isPassword && (
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="px-3 text-textSecondary"
            tabIndex={-1}
            aria-label={show ? 'Hide password' : 'Show password'}
          >
            <EyeIcon off={show} />
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-[13px] leading-snug text-error">{error}</p>}
    </div>
  );
}
