import { useEffect, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { toast } from '@/store/toastStore';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { ActionButton } from '@/components/ui/ActionButton';
import { Spinner } from '@/components/ui/Spinner';
import {
  completeOAuthRequest,
  denyOAuthRequest,
  getOAuthRequest,
} from '@/api/oauth';
import { apiErrorMessage } from '@/lib/apiClient';
import type { OAuthRequest } from '@/types/models';

// OAuth consent screen for one-click MCP login. Reached from the backend
// authorize endpoint with ?request_id=. Works signed-out (offers login first)
// and signed-in (approve/deny). Approve/deny navigates to the client's
// redirect URL returned by the backend.
const SCOPE_DESCRIPTIONS: Record<string, string> = {
  read: 'View your videos, catalog, and account details.',
  write: 'Create videos, upload files, and manage your content. Generations spend credits.',
};

function GoogleIcon() {
  return <img src="/icons/google.svg" width={22} height={22} alt="" />;
}

export default function ConsentScreen() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signInWithGoogle } = useAuth();
  const requestId = params.get('request_id');

  const [request, setRequest] = useState<OAuthRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loggingIn, setLoggingIn] = useState(false);

  useEffect(() => {
    if (!requestId) {
      setLoadError('This authorization link is missing its request id.');
      setLoading(false);
      return;
    }
    let cancelled = false;
    getOAuthRequest(requestId).then(
      (r) => {
        if (!cancelled) {
          setRequest(r);
          setLoading(false);
        }
      },
      (e: unknown) => {
        if (!cancelled) {
          setLoadError(
            `${apiErrorMessage(e)} The link may have expired; start over from your AI app.`,
          );
          setLoading(false);
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  if (loading) {
    return (
      <AuthLayout title="Connecting your AI assistant">
        <Spinner size={28} />
      </AuthLayout>
    );
  }

  if (loadError || !request) {
    return (
      <AuthLayout
        title="Link expired"
        subtitle={loadError ?? 'This authorization link is invalid.'}
      >
        <p className="text-sm leading-relaxed text-textSecondary">
          Go back to your AI app and start the connection again to get a fresh link.
        </p>
      </AuthLayout>
    );
  }

  const clientName = request.clientName ?? 'An AI assistant';
  const returnTo = `${location.pathname}${location.search}`;

  const google = async () => {
    setLoggingIn(true);
    try {
      await signInWithGoogle();
    } catch (e) {
      toast(`Google Sign-In failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoggingIn(false);
    }
  };

  const runAndRedirect = async (action: () => Promise<string>) => {
    if (!requestId) return;
    setBusy(true);
    try {
      window.location.href = await action();
    } catch (e) {
      toast(apiErrorMessage(e));
      setBusy(false);
    }
  };

  const scopeList = (
    <ul className="flex flex-col gap-2.5">
      {request.scopes.map((scope) => (
        <li key={scope} className="flex gap-2.5 text-sm leading-relaxed text-textPrimary">
          <span aria-hidden className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-neon" />
          {SCOPE_DESCRIPTIONS[scope] ?? `The "${scope}" permission.`}
        </li>
      ))}
    </ul>
  );

  if (!user) {
    return (
      <AuthLayout
        title={`Connect ${clientName}?`}
        subtitle={`${clientName} wants to access your pdftoreel account. Log in first, then review what it can do.`}
      >
        {scopeList}
        <ActionButton
          text="Continue with Google"
          backgroundColor="var(--color-neon)"
          textColor="var(--color-background)"
          fontWeight={600}
          icon={<GoogleIcon />}
          isLoading={loggingIn}
          onClick={google}
        />
        <button
          type="button"
          onClick={() => {
            sessionStorage.setItem('oauth.returnTo', returnTo);
            navigate('/login');
          }}
          className="text-center text-sm font-medium text-textSecondary hover:text-textPrimary"
        >
          Use email instead
        </button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={`Connect ${clientName}?`}
      subtitle={`${clientName} wants to access your pdftoreel account (${user.email ?? 'no email'}).`}
    >
      {scopeList}
      <ActionButton
        text="Allow access"
        backgroundColor="var(--color-neon)"
        textColor="var(--color-background)"
        fontWeight={600}
        isLoading={busy}
        onClick={() => runAndRedirect(() => completeOAuthRequest(request.requestId))}
      />
      <ActionButton
        text="Deny"
        backgroundColor="var(--color-surface1)"
        textColor="var(--color-textPrimary)"
        borderColor="var(--color-surface3)"
        hoverBackground="var(--color-surface2)"
        disabled={busy}
        onClick={() => runAndRedirect(() => denyOAuthRequest(request.requestId))}
      />
      <p className="text-center text-xs leading-relaxed text-textSecondary/70">
        You can revoke access anytime in Account, under Connected apps.
      </p>
    </AuthLayout>
  );
}
