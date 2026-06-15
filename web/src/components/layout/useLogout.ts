import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth/AuthProvider';
import { useUiStore } from '@/store/uiStore';

// Clears local generation state + cached server data, then signs out (mirrors
// the Flutter logout which reset the selection providers before signOut).
export function useLogout() {
  const { signOut } = useAuth();
  const queryClient = useQueryClient();
  return useCallback(async () => {
    useUiStore.getState().resetOnLogout();
    await signOut();
    queryClient.clear();
  }, [signOut, queryClient]);
}
