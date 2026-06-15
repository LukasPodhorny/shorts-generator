import { useNavigate } from 'react-router-dom';

// Pill-style back button (originally defined inside AuthLayout). Defaults to
// going back in history; pass `onClick` to override the destination.
export function BackButton({ onClick }: { onClick?: () => void }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={onClick ?? (() => navigate(-1))}
      className="flex h-10 items-center gap-1.5 rounded-full pr-3.5 pl-1 text-textPrimary  hover:bg-surface2"
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M15 18l-6-6 6-6" />
      </svg>
      <span className="text-sm font-medium">Back</span>
    </button>
  );
}
