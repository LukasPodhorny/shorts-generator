import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from '@/auth/AuthProvider';
import { SplashLoading } from '@/components/SplashLoading';
import { AppShell } from '@/components/AppShell';
import LoginScreen from '@/screens/auth/LoginScreen';
import CreateAccountScreen from '@/screens/auth/CreateAccountScreen';
import CreatePasswordScreen from '@/screens/auth/CreatePasswordScreen';
import EmailLoginScreen from '@/screens/auth/EmailLoginScreen';
import LoginPasswordScreen from '@/screens/auth/LoginPasswordScreen';
import VerifyEmailScreen from '@/screens/auth/VerifyEmailScreen';
import ChatGenerate from '@/screens/generate/ChatGenerate';
import GenerateScreen from '@/screens/generate/GenerateScreen';
import VideosScreen from '@/screens/videos/VideosScreen';
import SeriesDetailScreen from '@/screens/videos/SeriesDetailScreen';
import VideoPlayerScreen, { PublicVideoPlayerScreen } from '@/screens/videos/VideoPlayerScreen';
import AccountScreen from '@/screens/account/AccountScreen';
import ConsentScreen from '@/screens/oauth/ConsentScreen';
import PreviewGenerate from '@/screens/PreviewGenerate';
import SeedSeriesLayout from '@/screens/PreviewVideosData';
import InvitePendingScreen from '@/screens/auth/InvitePendingScreen';
import { useUserProfile } from '@/hooks/queries';
import axios from 'axios';

/**
 * Auth gate for account routes; public watch links bypass it.
 *   - initializing            -> splash
 *   - signed out              -> auth routes
 *   - signed in, unverified   -> verify-email gate (Google users are verified)
 *   - signed in, verified     -> the app shell
 */
export default function App() {
  const { pathname } = useLocation();
  if (pathname.startsWith('/watch/')) {
    return <Routes><Route path="/watch/:shareToken" element={<PublicVideoPlayerScreen />} /></Routes>;
  }
  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const { user, initializing } = useAuth();
  const { data: profile, error: profileError, isPending: profilePending, refetch: refetchProfile } = useUserProfile();

  // Where to go after login/signup. Set by screens that link into auth
  // (e.g. the OAuth consent screen) via sessionStorage so it survives the
  // multi-step email flows. Same-app paths only. Cleared once consumed.
  const storedReturnTo = sessionStorage.getItem('oauth.returnTo');
  const returnTo =
    storedReturnTo !== null &&
    storedReturnTo.startsWith('/') &&
    !storedReturnTo.startsWith('//')
      ? storedReturnTo
      : null;
  if (returnTo && user) {
    sessionStorage.removeItem('oauth.returnTo');
  }

  // DEV-ONLY: lets screens be viewed (inside the real shell) before signing in.
  // Auth'd API calls will be empty/errored without a session. Remove when done.
  if (import.meta.env.DEV && window.location.pathname.startsWith('/preview')) {
    return (
      <Routes>
        <Route path="/preview/generate-bare" element={<PreviewGenerate />} />
        <Route element={<SeedSeriesLayout />}>
          <Route path="/preview" element={<AppShell />}>
            <Route path="generate" element={<ChatGenerate />} />
            <Route path="studio" element={<GenerateScreen />} />
            <Route path="videos" element={<VideosScreen />} />
            <Route path="videos/:seriesId" element={<SeriesDetailScreen />} />
            <Route path="account" element={<AccountScreen />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/preview/generate" replace />} />
      </Routes>
    );
  }

  if (initializing) return <SplashLoading />;

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/login/email" element={<EmailLoginScreen />} />
        <Route path="/login/password" element={<LoginPasswordScreen />} />
        <Route path="/signup" element={<CreateAccountScreen />} />
        <Route path="/signup/password" element={<CreatePasswordScreen />} />
        <Route path="/oauth/consent" element={<ConsentScreen />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  if (!user.emailVerified) {
    if (returnTo) {
      return <Navigate to={returnTo} replace />;
    }
    return (
      <Routes>
        <Route path="/verify" element={<VerifyEmailScreen />} />
        <Route path="/oauth/consent" element={<ConsentScreen />} />
        <Route path="*" element={<Navigate to="/verify" replace />} />
      </Routes>
    );
  }

  if (profilePending) return <SplashLoading />;
  if (axios.isAxiosError(profileError) && profileError.response?.status === 403) {
    return <InvitePendingScreen />;
  }
  if (!profile) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-background text-textPrimary">
        <p>Could not check your access.</p>
        <button className="underline" onClick={() => void refetchProfile()}>Try again</button>
      </div>
    );
  }

  if (returnTo) {
    return <Navigate to={returnTo} replace />;
  }

  return (
    <Routes>
      {/* Full-screen player, outside the shell. */}
      <Route path="/videos/:seriesId/:reelId" element={<VideoPlayerScreen />} />
      <Route path="/oauth/consent" element={<ConsentScreen />} />
      <Route element={<AppShell />}>
        <Route index element={<ChatGenerate />} />
        <Route path="studio" element={profile.role === 'admin' ? <GenerateScreen /> : <Navigate to="/" replace />} />
        <Route path="videos" element={<VideosScreen />} />
        <Route path="videos/:seriesId" element={<SeriesDetailScreen />} />
        <Route path="account" element={<AccountScreen />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
