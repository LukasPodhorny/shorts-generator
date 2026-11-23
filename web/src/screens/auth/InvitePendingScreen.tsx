import { useAuth } from '@/auth/AuthProvider';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { ActionButton } from '@/components/ui/ActionButton';

export default function InvitePendingScreen() {
  const { user, signOut } = useAuth();

  return (
    <AuthLayout title="Invite only" subtitle="PDF to Reel is currently available by approval.">
      <p className="text-sm leading-relaxed text-textSecondary">
        {user?.email ? `${user.email} has not been approved yet. ` : ''}
        To request access, email{' '}
        <a className="font-semibold text-textPrimary underline" href="mailto:support@pdftoreel.com">
          support@pdftoreel.com
        </a>
        . If you have already been approved, refresh this page.
      </p>
      <ActionButton
        text="Use another account"
        backgroundColor="var(--color-surface2)"
        textColor="var(--color-textPrimary)"
        onClick={() => void signOut()}
      />
    </AuthLayout>
  );
}
