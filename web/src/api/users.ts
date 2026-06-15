import { api } from '@/lib/apiClient';
import { parseUserProfile, type UserProfile } from '@/types/models';

// Ports lib/services/user_service.dart.

export async function getMe(): Promise<UserProfile> {
  const { data } = await api.get('/api/users/me');
  return parseUserProfile(data as Record<string, unknown>);
}

// NOTE: the backend route POST /api/users/add-credits is currently commented
// out. Ported for parity but intentionally not wired to any UI.
export async function addCredits(amount: number): Promise<void> {
  await api.post('/api/users/add-credits', { amount });
}
