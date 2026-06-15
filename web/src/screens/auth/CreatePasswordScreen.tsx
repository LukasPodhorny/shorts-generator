import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { useAuthFlowStore } from '@/store/authFlowStore';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { InputField } from '@/components/auth/InputField';
import { ActionButton } from '@/components/ui/ActionButton';

function friendlySignupError(e: unknown): string {
  const raw = String(e);
  if (raw.includes('email-already-in-use'))
    return 'An account with this email already exists. Try logging in.';
  if (raw.includes('weak-password')) return 'This password is too weak. Pick a longer one.';
  if (raw.includes('network')) return 'No connection. Check your internet and try again.';
  return 'Could not create your account. Please try again.';
}

export default function CreatePasswordScreen() {
  const navigate = useNavigate();
  const { createAccount } = useAuth();
  const email = useAuthFlowStore((s) => s.email);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // If the email step was skipped (e.g. page refresh), restart the flow.
  useEffect(() => {
    if (!email) navigate('/signup', { replace: true });
  }, [email, navigate]);

  const signUp = async () => {
    setPasswordError(null);
    setConfirmError(null);
    if (password.length < 6) {
      setPasswordError('Password must be at least 6 characters');
      return;
    }
    if (password !== confirm) {
      setConfirmError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await createAccount(email, password);
      // Auth state changes; App routes to the verify-email gate automatically.
    } catch (e) {
      setConfirmError(friendlySignupError(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Create password" subtitle="Pick something at least 6 characters long.">
      <InputField
        label="Password"
        hint="At least 6 characters"
        isPassword
        autoFocus
        value={password}
        onChange={setPassword}
        error={passwordError}
      />
      <InputField
        label="Confirm password"
        hint="Repeat your password"
        isPassword
        value={confirm}
        onChange={setConfirm}
        error={confirmError}
        onSubmit={signUp}
      />
      <ActionButton
        text="Create account"
        backgroundColor="var(--color-neon)"
        textColor="var(--color-background)"
        fontWeight={600}
        isLoading={loading}
        onClick={signUp}
      />
    </AuthLayout>
  );
}
