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
import GenerateScreen from '@/screens/generate/GenerateScreen';
import VideosScreen from '@/screens/videos/VideosScreen';
import SeriesDetailScreen from '@/screens/videos/SeriesDetailScreen';
import VideoPlayerScreen from '@/screens/videos/VideoPlayerScreen';
import AccountScreen from '@/screens/account/AccountScreen';
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

  // DEV-ONLY: lets screens be viewed (inside the real shell) before signing in.
  // Auth'd API calls will be empty/errored without a session. Remove when done.
  if (import.meta.env.DEV && window.location.pathname.startsWith('/preview')) {
    return (
      <Routes>
        <Route path="/preview/generate-bare" element={<PreviewGenerate />} />
        <Route element={<SeedSeriesLayout />}>
          <Route path="/preview" element={<AppShell />}>
            <Route path="generate" element={<GenerateScreen />} />
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
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  if (!user.emailVerified) {
    return (
      <Routes>
        <Route path="/verify" element={<VerifyEmailScreen />} />
        <Route path="*" element={<Navigate to="/verify" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      {/* Full-screen player, outside the shell. */}
      <Route path="/videos/:seriesId/:reelId" element={<VideoPlayerScreen />} />
      <Route element={<AppShell />}>
        <Route index element={<GenerateScreen />} />
        <Route path="videos" element={<VideosScreen />} />
        <Route path="videos/:seriesId" element={<SeriesDetailScreen />} />
        <Route path="account" element={<AccountScreen />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
