import { api } from '@/lib/apiClient';

export async function listInvites(): Promise<string[]> {
  const { data } = await api.get<{ email: string }[]>('/api/admin/invites');
  return data.map((invite) => invite.email);
}

export async function approveInvite(email: string): Promise<void> {
  await api.post('/api/admin/invites', { email });
}

export async function revokeInvite(email: string): Promise<void> {
  await api.delete(`/api/admin/invites/${encodeURIComponent(email)}`);
}
