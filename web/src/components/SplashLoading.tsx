import { AssembleLogo } from '@/components/ui/AssembleLogo';

/** Full-screen splash shown while Firebase resolves the initial auth state. */
export function SplashLoading() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-background scale-75">
      <AssembleLogo />
    </div>
  );
}
