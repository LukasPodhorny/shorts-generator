import type { ReactNode } from 'react';
import { useIsDesktop } from '@/hooks/useBreakpoint';
import { MaskIcon } from '@/components/ui/MaskIcon';
import { BackButton } from '@/components/ui/BackButton';
import { AuthBackground } from './AuthBackground';

// Port of AuthLayout: a desktop centered card vs a mobile scrolling page, both
// with a back button and the marbled background.
export function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const isDesktop = useIsDesktop();

  if (isDesktop) {
    return (
      <div className="relative h-full w-full overflow-auto bg-background">
        <AuthBackground />
        <div className="absolute left-3 top-3 z-10">
          <BackButton />
        </div>
        <div className="relative flex min-h-full items-center justify-center p-12">
          <div className="w-full max-w-[440px] rounded-[20px] border border-surface3/40 bg-surface1 p-10">
            <MaskIcon src="/icons/logo.svg" size={36} color="var(--color-neon)" />
            <h1 className="mt-6 text-2xl font-semibold tracking-[-0.4px] text-textPrimary">
              {title}
            </h1>
            {subtitle && (
              <p className="mt-2 text-[15px] leading-relaxed text-textSecondary">{subtitle}</p>
            )}
            <div className="mt-7 flex flex-col gap-4">{children}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full overflow-auto bg-background">
      <AuthBackground />
      <div className="relative px-6 pb-6 pt-3">
        <BackButton />
        <h1 className="mt-4 text-[28px] font-semibold leading-tight tracking-[-0.5px] text-textPrimary">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-2 text-[15px] leading-relaxed text-textSecondary">{subtitle}</p>
        )}
        <div className="mt-8 flex flex-col gap-4">{children}</div>
      </div>
    </div>
  );
}
