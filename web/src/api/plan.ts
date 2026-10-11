import { api } from '@/lib/apiClient';

// Client for the chatbot-style entry point (POST /api/plan). The backend's
// intent parser turns one freeform instruction + the attachments the user added
// in the UI into a full generation, filling in any config the user didn't pick.
// Manual choices passed here always win over the parser's inferences.

export type PlanAttachment =
  | { type: 'file'; name: string; key: string }
  | { type: 'link'; url: string };

export interface StartPlanArgs {
  instruction: string;
  attachments: PlanAttachment[];
  // Optional manual overrides. Omit any the user left for the AI to decide.
  templateName?: string | null;
  avatarNames?: string[] | null;
  amount?: number | null;
  enabledTags?: string[] | null;
  configName?: string | null;
}

export async function startPlan(args: StartPlanArgs): Promise<number> {
  const body: Record<string, unknown> = {
    instruction: args.instruction,
    attachments: args.attachments,
  };
  if (args.templateName) body.template_name = args.templateName;
  if (args.avatarNames && args.avatarNames.length > 0) {
    body.avatar_names = args.avatarNames;
  }
  if (args.amount != null) body.amount = args.amount;
  if (args.enabledTags != null) body.enabled_tags = args.enabledTags;
  if (args.configName) body.config_name = args.configName;

  const { data } = await api.post('/api/plan', body);
  return (data as { series_id: number }).series_id;
}
