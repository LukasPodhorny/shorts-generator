import { api } from '@/lib/apiClient';
import {
  parseOAuthGrant,
  parseOAuthRequest,
  type OAuthGrant,
  type OAuthRequest,
} from '@/types/models';

// OAuth consent + connected-apps management (backend: api/routers/oauth.py).

export async function getOAuthRequest(requestId: string): Promise<OAuthRequest> {
  const { data } = await api.get(`/api/oauth/request/${requestId}`);
  return parseOAuthRequest(data as Record<string, unknown>);
}

export async function completeOAuthRequest(requestId: string): Promise<string> {
  const { data } = await api.post('/api/oauth/complete', { request_id: requestId });
  return (data as { redirect_url: string }).redirect_url;
}

export async function denyOAuthRequest(requestId: string): Promise<string> {
  const { data } = await api.post('/api/oauth/deny', { request_id: requestId });
  return (data as { redirect_url: string }).redirect_url;
}

export async function listOAuthGrants(): Promise<OAuthGrant[]> {
  const { data } = await api.get('/api/oauth/grants');
  return (data as Record<string, unknown>[]).map(parseOAuthGrant);
}

export async function revokeOAuthGrant(grantId: number): Promise<void> {
  await api.delete(`/api/oauth/grants/${grantId}`);
}
