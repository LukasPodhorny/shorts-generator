import { Navigate, Route, Routes } from 'react-router-dom';
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
import VideoPlayerScreen from '@/screens/videos/VideoPlayerScreen';
import AccountScreen from '@/screens/account/AccountScreen';
import ConsentScreen from '@/screens/oauth/ConsentScreen';
import PreviewGenerate from '@/screens/PreviewGenerate';
import SeedSeriesLayout from '@/screens/PreviewVideosData';

/**
 * Top-level auth gate, mirroring MyApp's authStateChanges StreamBuilder:
 *   - initializing            -> splash
 *   - signed out              -> auth routes
 *   - signed in, unverified   -> verify-email gate (Google users are verified)
 *   - signed in, verified     -> the app shell
 */
export default function App() {
  const { user, initializing } = useAuth();

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
    // Consent stays reachable mid-verification; approving needs no verified email.
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
        <Route path="studio" element={<GenerateScreen />} />
        <Route path="videos" element={<VideosScreen />} />
        <Route path="videos/:seriesId" element={<SeriesDetailScreen />} />
        <Route path="account" element={<AccountScreen />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
