import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { useAuthFlowStore } from '@/store/authFlowStore';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { InputField } from '@/components/auth/InputField';
import { ActionButton } from '@/components/ui/ActionButton';

export default function EmailLoginScreen() {
  const navigate = useNavigate();
  const { checkIfUserExists } = useAuth();
  const setEmail = useAuthFlowStore((s) => s.setEmail);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onContinue = async () => {
    const email = value.trim();
    if (!email.includes('@')) {
      setError('Please enter a valid email address');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const exists = await checkIfUserExists(email);
      if (exists) {
        setEmail(email);
        navigate('/login/password');
      } else {
        setError('No account found with this email.');
      }
    } catch {
      setError('Error checking email. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Log in with the email you signed up with.">
      <InputField
        label="Email"
        hint="you@example.com"
        type="email"
        autoFocus
        value={value}
        onChange={(v) => {
          setValue(v);
          if (error) setError(null);
        }}
        error={error}
        onSubmit={onContinue}
      />
      <ActionButton
        text="Continue"
        backgroundColor="var(--color-neon)"
        textColor="var(--color-background)"
        fontWeight={600}
        isLoading={loading}
        onClick={onContinue}
      />
    </AuthLayout>
  );
}
