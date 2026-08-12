export interface PipelineStats {
  jobs_tracked: number;
  applications_sent: number;
  interviews_scheduled: number;
  offers_received: number;
  response_rate: number;
  avg_days_to_interview: number;
}

export interface SecurityStatus {
  tenant_id: string;
  rls_enforced: boolean;
  policy_prohibitions_count: number;
  prohibitions: string[];
  circuit_breaker: {
    action_counts: { applies: number; emails: number };
    limits: { applies: number; emails: number };
  };
  kms_vault_status: string;
}

export interface Job {
  title: string;
  company: string;
  location: string;
  tier: number | null;
  ev_score: number | null;
  match_score: number | null;
  [key: string]: unknown;
}

export interface ActionItem {
  action_id: string;
  action_type: string;
  band: string;
  status: string;
  payload: Record<string, unknown>;
}
