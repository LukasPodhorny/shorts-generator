import {
  createContext,
  use,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  createUserWithEmailAndPassword as fbCreateUser,
  onAuthStateChanged,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword as fbSignIn,
  signInWithPopup,
  signOut as fbSignOut,
  type User,
} from 'firebase/auth';
import { auth, googleProvider } from '@/lib/firebase';

interface AuthContextValue {
  user: User | null;
  /** True until the first Firebase auth-state callback resolves. */
  initializing: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  /** Whether an account exists for this email (best-effort, mirrors Flutter). */
  checkIfUserExists: (email: string) => Promise<boolean>;
  createAccount: (email: string, password: string) => Promise<void>;
  sendVerificationEmail: () => Promise<void>;
  sendPasswordReset: (email: string) => Promise<void>;
  reloadUser: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    return onAuthStateChanged(auth, (u) => {
      setUser(u);
      setInitializing(false);
    });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      initializing,
      signInWithGoogle: async () => {
        await signInWithPopup(auth, googleProvider);
      },
      signInWithEmail: async (email, password) => {
        await fbSignIn(auth, email, password);
      },
      checkIfUserExists: async (email) => {
        // Mirrors the Flutter workaround: attempt sign-in with a dummy password.
        // 'user-not-found' => no account; anything else (wrong password, etc.)
        // => assume it exists so the flow can continue.
        try {
          await fbSignIn(auth, email, 'dummy_password_for_existence_check_123!');
          return true;
        } catch (e) {
          const code = (e as { code?: string }).code ?? '';
          return code !== 'auth/user-not-found';
        }
      },
      createAccount: async (email, password) => {
        const cred = await fbCreateUser(auth, email, password);
        if (cred.user) await sendEmailVerification(cred.user);
      },
      sendVerificationEmail: async () => {
        if (auth.currentUser) await sendEmailVerification(auth.currentUser);
      },
      sendPasswordReset: async (email) => {
        await sendPasswordResetEmail(auth, email);
      },
      reloadUser: async () => {
        await auth.currentUser?.reload();
        // reload() mutates currentUser in place; re-set to trigger re-render.
        setUser(auth.currentUser ? { ...auth.currentUser } as User : null);
      },
      signOut: async () => {
        await fbSignOut(auth);
      },
    }),
    [user, initializing],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthContextValue {
  const ctx = use(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}
