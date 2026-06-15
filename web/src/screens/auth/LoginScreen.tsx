import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { useIsDesktop } from '@/hooks/useBreakpoint';
import { toast } from '@/store/toastStore';
import { AuthBackground } from '@/components/auth/AuthBackground';
import { ActionButton } from '@/components/ui/ActionButton';
import { MaskIcon } from '@/components/ui/MaskIcon';

const TERMS = 'By continuing you agree to our Terms & Privacy Policy';

function GoogleIcon() {
  return <img src="/icons/google.svg" width={22} height={22} alt="" />;
}
function MailIcon() {
  return <MaskIcon src="/icons/mail.svg" size={20} color="var(--color-textPrimary)" />;
}

function OrDivider() {
  return (
    <div className="flex items-center">
      <div className="h-px flex-1 bg-surface3/50" />
      <span className="px-3.5 text-[13px] tracking-[0.3px] text-textSecondary">or</span>
      <div className="h-px flex-1 bg-surface3/50" />
    </div>
  );
}

// Entry login screen. Desktop: a centered card. Mobile: brand up top with an
// actions panel pinned to the bottom (ports DesktopLoginScreen + LoginScreen).
export default function LoginScreen() {
  const navigate = useNavigate();
  const { signInWithGoogle } = useAuth();
  const isDesktop = useIsDesktop();
  const [loading, setLoading] = useState(false);

  const google = async () => {
    setLoading(true);
    try {
      await signInWithGoogle();
    } catch (e) {
      toast(`Google Sign-In failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoading(false);
    }
  };

  const actions = (
    <>
      <ActionButton
        text="Continue with Google"
        backgroundColor="var(--color-neon)"
        textColor="var(--color-background)"
        fontWeight={600}
        icon={<GoogleIcon />}
        isLoading={loading}
        onClick={google}
      />
      <ActionButton
        text="Sign up with email"
        backgroundColor="var(--color-surface2)"
        textColor="var(--color-textPrimary)"
        hoverBackground="var(--color-surface3)"
        icon={<MailIcon />}
        onClick={() => navigate('/signup')}
      />
      <OrDivider />
      <ActionButton
        text="Log in"
        backgroundColor="var(--color-surface1)"
        textColor="var(--color-textPrimary)"
        borderColor="var(--color-surface3)"
        hoverBackground="var(--color-surface2)"
        onClick={() => navigate('/login/email')}
      />
    </>
  );

  if (isDesktop) {
    return (
      <div className="relative h-full w-full overflow-auto bg-background">
        <AuthBackground />
        <div className="relative flex min-h-full items-center justify-center p-12">
          <div className="w-full max-w-[440px] rounded-3xl border border-surface3/40 bg-surface1 px-11 py-12">
            <div className="flex flex-col items-center text-center">
              <MaskIcon src="/icons/logo.svg" size={64} color="var(--color-neon)" />
              <h1 className="mt-7 text-[28px] font-semibold tracking-[-0.4px] text-textPrimary">
                PDF to Reel
              </h1>
              <p className="mt-2.5 text-[15px] text-textSecondary">
                Turn one prompt into engaging videos.
              </p>
            </div>
            <div className="mt-10 flex flex-col gap-3">{actions}</div>
            <p className="mt-7 text-center text-xs leading-relaxed text-textSecondary/70">{TERMS}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-background">
      <AuthBackground />
      <div className="relative flex flex-1 flex-col items-center justify-center px-7 text-center">
        <MaskIcon src="/icons/logo.svg" size={120} color="var(--color-neon)" />
        <h1 className="mt-7 text-[32px] font-semibold tracking-[-0.5px] text-textPrimary">
          PDF to Reel
        </h1>
        <p className="mt-2.5 text-[15px] leading-relaxed text-textSecondary">
          Turn just one prompt/file into
          <br />
          engaging videos with AI.
        </p>
      </div>
      <div className="relative rounded-t-[20px] border-t border-surface1 bg-background px-7 pb-4 pt-6">
        <div className="flex flex-col gap-3">{actions}</div>
        <p className="mt-6 text-center text-xs leading-relaxed text-textSecondary/70">{TERMS}</p>
      </div>
    </div>
  );
}
