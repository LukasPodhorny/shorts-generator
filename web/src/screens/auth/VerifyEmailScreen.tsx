import { useEffect, useState } from 'react';
import { useAuth } from '@/auth/AuthProvider';
import { auth } from '@/lib/firebase';
import { toast } from '@/store/toastStore';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { ActionButton } from '@/components/ui/ActionButton';
import { Spinner } from '@/components/ui/Spinner';

// Port of EnterCodeScreen: polls every 3s for email verification. When the user
// becomes verified, reloadUser updates auth state and App routes into the app.
export default function VerifyEmailScreen() {
  const { user, reloadUser, sendVerificationEmail, signOut } = useAuth();
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const id = setInterval(() => {
      void reloadUser();
    }, 3000);
    return () => clearInterval(id);
  }, [reloadUser]);

  const checkNow = async () => {
    setChecking(true);
    await reloadUser();
    setChecking(false);
    // reloadUser refreshes auth.currentUser in place; read the flag directly.
    if (!auth.currentUser?.emailVerified) {
      toast('Email not verified yet. Please check your inbox.');
    }
  };

  const resend = async () => {
    try {
      await sendVerificationEmail();
      toast('Verification email resent!');
    } catch (e) {
      toast(`Error: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <AuthLayout
      title="Verify your email"
      subtitle={
        user?.email
          ? `We've sent a verification link to ${user.email}. Click the link in the email to continue.`
          : "We've sent you a verification link. Click it in your inbox to continue."
      }
    >
      <div className="flex items-center gap-3 rounded-[14px] border border-surface3/50 bg-surface1/60 px-4 py-3.5">
        <span className="text-neon">✉️</span>
        <span className="flex-1 text-sm font-medium text-textPrimary">
          Waiting for verification…
        </span>
        <Spinner size={16} strokeWidth={2} style={{ color: 'var(--color-neon)' }} />
      </div>
      <ActionButton
        text="I have verified"
        backgroundColor="var(--color-neon)"
        textColor="var(--color-background)"
        fontWeight={600}
        isLoading={checking}
        onClick={checkNow}
      />
      <ActionButton
        text="Resend email"
        backgroundColor="transparent"
        textColor="var(--color-textPrimary)"
        borderColor="var(--color-surface3)"
        onClick={resend}
      />
      <button
        type="button"
        onClick={() => void signOut()}
        className="mx-auto px-3 py-1.5 text-[13px] font-medium text-textSecondary hover:text-textPrimary"
      >
        Back to login
      </button>
    </AuthLayout>
  );
}
