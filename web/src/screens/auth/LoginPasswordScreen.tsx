import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { useAuthFlowStore } from '@/store/authFlowStore';
import { toast } from '@/store/toastStore';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { InputField } from '@/components/auth/InputField';
import { ActionButton } from '@/components/ui/ActionButton';

function friendlyAuthError(e: unknown): string {
  const raw = String(e);
  if (raw.includes('wrong-password') || raw.includes('invalid-credential'))
    return 'Incorrect password. Try again or reset it below.';
  if (raw.includes('too-many-requests')) return 'Too many attempts. Wait a moment, then try again.';
  if (raw.includes('network')) return 'No connection. Check your internet and try again.';
  return 'Could not log you in. Please try again.';
}

export default function LoginPasswordScreen() {
  const navigate = useNavigate();
  const { signInWithEmail, sendPasswordReset } = useAuth();
  const email = useAuthFlowStore((s) => s.email);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!email) navigate('/login/email', { replace: true });
  }, [email, navigate]);

  const login = async () => {
    if (!password) {
      setError('Please enter your password');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await signInWithEmail(email, password);
    } catch (e) {
      setError(friendlyAuthError(e));
    } finally {
      setLoading(false);
    }
  };

  const forgot = async () => {
    if (!email) return;
    try {
      await sendPasswordReset(email);
      toast('Password reset email sent!');
    } catch (e) {
      toast(`Error: ${e instanceof Error ? e.message : e}`);
    }
  };

  return (
    <AuthLayout title="Enter password" subtitle={email ? `Signing in as ${email}` : undefined}>
      <InputField
        label="Password"
        hint="Enter your password"
        isPassword
        autoFocus
        value={password}
        onChange={setPassword}
        error={error}
        onSubmit={login}
      />
      <div className="-mt-2 flex justify-end">
        <button
          type="button"
          onClick={forgot}
          className="px-2 py-1 text-[13px] font-medium text-textSecondary hover:text-textPrimary"
        >
          Forgot password?
        </button>
      </div>
      <ActionButton
        text="Log in"
        backgroundColor="var(--color-neon)"
        textColor="var(--color-background)"
        fontWeight={600}
        isLoading={loading}
        onClick={login}
      />
    </AuthLayout>
  );
}
