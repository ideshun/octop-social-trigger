export type SocialTriggerPromptKey =
  | "contextHeader"
  | "automaticHeader"
  | "directHeader"
  | "automaticHintHeader"
  | "directHintHeader"
  | "quoteHeader"
  | "currentHeader"
  | "automaticHint"
  | "directHint"
  | "decisionPrompt";

export interface SocialTriggerPolicy {
  prompts?: Partial<Record<SocialTriggerPromptKey, string>>;
  blockedTerms?: string[];
  mode: "disabled" | "mention_only" | "smart" | "probability" | "always";
  replyProbability: number;
  smartScoreThreshold: number;
  decisionModelEnabled?: boolean;
  decisionModelTimeoutMs?: number;
  decisionModelMaxCallsPerDay?: number;
  cooldownSeconds: number;
  maxPassiveRepliesPerHour: number;
  maxPassiveRepliesPerDay: number;
  maxConsecutiveReplies: number;
  maxBotReplyRatio: number;
  randomDelayMinMs: number;
  randomDelayMaxMs: number;
  debounceMs: number;
  contextMessages: number;
  contextTtlSeconds: number;
  mentionBypassCooldown: boolean;
  quietHours: { enabled: boolean; start: string; end: string };
}

export type SocialTriggerScope =
  | "defaults"
  | "channelTypes"
  | "channelInstances"
  | "groups"
  | "groupAgents";

export interface SocialTriggerPolicySettings {
  policy: SocialTriggerPolicy;
  inheritedPolicy: SocialTriggerPolicy;
  overrides: Partial<SocialTriggerPolicy>;
  allowed: boolean;
  policySource: Record<string, string>;
}

export interface SocialTriggerChannel {
  channelKind: string;
  channelId: string;
  channelName: string;
  agentId: string;
  settings: SocialTriggerPolicySettings;
}

export interface SocialTriggerGroup extends SocialTriggerChannel {
  groupId: string;
  groupName?: string | null;
  updatedAt: number;
  ready: boolean;
  channelEnabled: boolean;
  policyKnown?: boolean;
  groupPolicyEnabled: boolean;
  groupVisibility: string;
  channelParticipationEnabled: boolean;
  hostActivation: string;
  agentSettings: SocialTriggerPolicySettings;
}

export interface SocialTriggerSettings {
  enabled: boolean;
  dryRun: boolean;
  timezone: string;
  decisionModelSupported?: boolean;
  decisionModelConfigured?: boolean | null;
  promptSettingsSupported?: boolean;
  promptDefaults?: Record<string, Record<SocialTriggerPromptKey, string>>;
  recent: {
    reasonCode: string;
    event: string;
    decisionSource?: "model" | "rules" | "policy";
  } | null;
  defaults: SocialTriggerPolicySettings;
  channels: SocialTriggerChannel[];
  channelTypes: {
    channelKind: string;
    settings: SocialTriggerPolicySettings;
  }[];
  groups: SocialTriggerGroup[];
}
