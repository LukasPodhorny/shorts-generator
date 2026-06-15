import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthFlowStore } from '@/store/authFlowStore';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { InputField } from '@/components/auth/InputField';
import { ActionButton } from '@/components/ui/ActionButton';

export default function CreateAccountScreen() {
  const navigate = useNavigate();
  const setEmail = useAuthFlowStore((s) => s.setEmail);
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);

  const onContinue = () => {
    const email = value.trim();
    if (!email.includes('@') || !email.includes('.')) {
      setError('Please enter a valid email address');
      return;
    }
    setError(null);
    setEmail(email);
    navigate('/signup/password');
  };

  return (
    <AuthLayout title="Create account" subtitle="Sign up with your email to start creating.">
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
        onClick={onContinue}
      />
    </AuthLayout>
  );
}
