import type {
  SocialTriggerPolicy,
  SocialTriggerSettings,
  SocialTriggerScope,
  SocialTriggerPromptKey,
} from "./types";
import type * as ReactTypes from "react";
import type * as AntdTypes from "antd";
import zh from "./zh.json";
import en from "./en.json";
import cssText from "./settings.css";
export const css = cssText;
export interface SettingsHost {
  version: 1;
  React: typeof ReactTypes;
  ui: typeof AntdTypes;
  message: Pick<typeof AntdTypes.message, "success" | "error">;
  locale: string;
  request<T>(options?: RequestInit): Promise<T>;
}
export function createSettingsPanel(host: SettingsHost) {
  const React = host.React;
  const { useEffect, useState } = React;
  const {
    Alert,
    Button,
    Collapse,
    Form,
    Input,
    InputNumber,
    Modal,
    Pagination,
    Popconfirm,
    Select,
    Space,
    Spin,
    Switch,
    Tag,
  } = host.ui;
  const { message } = host;
  const pluginsApi = {
    getSocialTriggerSettings: () => host.request<SocialTriggerSettings>(),
    saveSocialTriggerSettings: (values: unknown) =>
      host.request<{ status: string }>({
        method: "PUT",
        body: JSON.stringify(values),
      }),
  };
  const translations = host.locale.startsWith("zh") ? zh : en;
  function useTranslation() {
    return {
      i18n: { resolvedLanguage: host.locale },
      t: (key: string, values?: Record<string, unknown>) => {
        const path = key.replace(/^plugins\.participation\./, "").split(".");
        const value = path.reduce<unknown>(
          (obj, part) =>
            obj && typeof obj === "object"
              ? (obj as Record<string, unknown>)[part]
              : undefined,
          translations,
        );
        return String(value ?? values?.defaultValue ?? key).replace(
          /\{\{(\w+)\}\}/g,
          (_, name) => String(values?.[name] ?? name),
        );
      },
    };
  }
  const styles = {
    root: "social-trigger-settings",
    description: "social-trigger-description",
    scope: "social-trigger-scope",
    scopeHeader: "social-trigger-scope-header",
    promptReset: "social-trigger-prompt-reset",
    promptHeader: "social-trigger-prompt-header",
  };
  type Values = SocialTriggerPolicy & { enabled: boolean; dryRun: boolean };
  const scopes: SocialTriggerScope[] = [
    "defaults",
    "channelTypes",
    "channelInstances",
    "groups",
    "groupAgents",
  ];
  const selectionStorageKey = "octop:social-trigger-selection";
  type Selection = {
    scope: SocialTriggerScope;
    kind: string;
    channelId: string;
    groupId: string;
    agentId: string;
  };

  function restoreSelection(result: SocialTriggerSettings): Selection {
    const first = result.groups[0] ?? result.channels[0];
    const fallback: Selection = {
      scope: "defaults",
      kind: first?.channelKind ?? "",
      channelId: first?.channelId ?? "",
      groupId: result.groups[0]?.groupId ?? "",
      agentId: first?.agentId ?? "",
    };
    try {
      const saved: Partial<Selection> | null = JSON.parse(
        localStorage.getItem(selectionStorageKey) ?? "null",
      );
      if (!saved?.scope || !scopes.includes(saved.scope)) return fallback;
      const kind = result.channelTypes.find(
        (item) => item.channelKind === saved.kind,
      );
      const channel = result.channels.find(
        (item) =>
          item.channelKind === saved.kind && item.channelId === saved.channelId,
      );
      const matchingGroups = result.groups.filter(
        (item) =>
          item.channelKind === saved.kind &&
          item.channelId === saved.channelId &&
          item.groupId === saved.groupId,
      );
      const group =
        matchingGroups.find((item) => item.agentId === saved.agentId) ??
        (saved.scope === "groupAgents" ? undefined : matchingGroups[0]);
      const valid = {
        defaults: true,
        channelTypes: !!kind,
        channelInstances: !!channel,
        groups: !!group,
        groupAgents: !!group,
      }[saved.scope];
      if (!valid) return fallback;
      const target =
        group ??
        channel ??
        result.channels.find(
          (item) => item.channelKind === kind?.channelKind,
        ) ??
        first;
      const viewedGroup =
        group ??
        result.groups.find(
          (item) =>
            item.channelKind === target?.channelKind &&
            item.channelId === target?.channelId,
        );
      return {
        scope: saved.scope,
        kind: target?.channelKind ?? "",
        channelId: target?.channelId ?? "",
        groupId: viewedGroup?.groupId ?? "",
        agentId: viewedGroup?.agentId ?? target?.agentId ?? "",
      };
    } catch {
      return fallback;
    }
  }

  const isZh = host.locale.startsWith("zh");
  const channelLabel = (kind: string) =>
    ({
      qq: "QQ",
      octo: "Octo",
      discord: "Discord",
      feishu: isZh ? "飞书 / Lark" : "Feishu / Lark",
      telegram: "Telegram",
      slack: "Slack",
      whatsapp: "WhatsApp",
      dingtalk: isZh ? "钉钉" : "DingTalk",
      wecom: isZh ? "企业微信" : "WeCom",
      weixin: isZh ? "微信" : "WeChat",
    })[kind] || kind;
  const grid = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
    gap: "0 16px",
  };

  const promptKeys: SocialTriggerPromptKey[] = [
    "contextHeader",
    "automaticHeader",
    "directHeader",
    "automaticHintHeader",
    "directHintHeader",
    "quoteHeader",
    "currentHeader",
    "automaticHint",
    "directHint",
    "decisionPrompt",
  ];

  const normalizeTerm = (term: string) => term.normalize("NFKC").toLowerCase();
  function mergeBlockedTerms(existing: string[], draft: string) {
    const terms = draft
      .split(/[,，;；\r\n]+/)
      .map((term) => term.trim())
      .filter(Boolean);
    if (terms.some((term) => [...term].length > 100)) {
      return { error: "blockedTermsTooLong" };
    }
    const seen = new Set(existing.map(normalizeTerm));
    const next = [...existing];
    for (const term of terms) {
      const key = normalizeTerm(term);
      if (!seen.has(key)) {
        seen.add(key);
        next.push(term);
      }
    }
    if (next.length > 5000) return { error: "blockedTermsTooMany" };
    return { terms: next };
  }

  function BlockedTermsEditor({
    id,
    value = [],
    onChange,
  }: {
    id?: string;
    value?: string[];
    onChange?: (terms: string[]) => void;
  }) {
    const { t } = useTranslation();
    const text = (key: string, values?: Record<string, unknown>) =>
      t(`plugins.participation.${key}`, values);
    const [open, setOpen] = useState(false);
    const [draft, setDraft] = useState("");
    const [page, setPage] = useState(1);
    const filtered = value
      .map((term, index) => ({ term, index }))
      .filter(({ term }) =>
        normalizeTerm(term).includes(normalizeTerm(draft.trim())),
      );
    const currentPage = Math.min(
      page,
      Math.max(1, Math.ceil(filtered.length / 50)),
    );

    const add = () => {
      if (!draft.trim()) return;
      const result = mergeBlockedTerms(value, draft);
      if (!result.terms) {
        message.error(text(result.error ?? "saveFailed"));
        return;
      }
      onChange?.(result.terms);
      setDraft("");
      setPage(1);
    };
    const finish = () => {
      setOpen(false);
      setDraft("");
      setPage(1);
    };

    return (
      <>
        <Space>
          <Button
            id={id}
            aria-label={text("blockedTermsManage")}
            onClick={() => setOpen(true)}
          >
            {text("blockedTermsManage")}
          </Button>
          <span>{text("blockedTermsCount", { count: value.length })}</span>
        </Space>
        <Modal
          title={text("blockedTermsManage")}
          open={open}
          onCancel={finish}
          footer={
            <Button
              type="primary"
              aria-label={text("blockedTermsDone")}
              onClick={finish}
            >
              {text("blockedTermsDone")}
            </Button>
          }
        >
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space.Compact style={{ width: "100%" }}>
              <Input
                allowClear
                aria-label={text("blockedTermsInput")}
                value={draft}
                placeholder={text("blockedTermsPlaceholder")}
                onChange={(event) => {
                  setDraft(event.target.value);
                  setPage(1);
                }}
                onPaste={(event) => {
                  const pasted = event.clipboardData.getData("text");
                  if (!/[\r\n]/.test(pasted)) return;
                  event.preventDefault();
                  const start =
                    event.currentTarget.selectionStart ?? draft.length;
                  const end = event.currentTarget.selectionEnd ?? start;
                  setDraft(
                    draft.slice(0, start) +
                      pasted.replace(/[\r\n]+/g, "，") +
                      draft.slice(end),
                  );
                  setPage(1);
                }}
                onPressEnter={(event) => {
                  event.preventDefault();
                  add();
                }}
              />
              <Button aria-label={text("blockedTermsAdd")} onClick={add}>
                {text("blockedTermsAdd")}
              </Button>
            </Space.Compact>
            <div style={{ color: "var(--ant-color-text-secondary)" }}>
              {draft.trim()
                ? text("blockedTermsMatchCount", {
                    count: filtered.length,
                    total: value.length,
                  })
                : text("blockedTermsCount", { count: value.length })}
            </div>
            {filtered.length > 0 ? (
              <div style={{ maxHeight: 240, overflowY: "auto" }}>
                <Space wrap>
                  {filtered
                    .slice((currentPage - 1) * 50, currentPage * 50)
                    .map(({ term, index }) => (
                      <Tag
                        key={`${index}:${term}`}
                        closable
                        closeIcon={
                          <button
                            type="button"
                            aria-label={text("blockedTermsRemove", { term })}
                            style={{
                              border: 0,
                              padding: 0,
                              background: "none",
                              cursor: "pointer",
                            }}
                          >
                            ×
                          </button>
                        }
                        onClose={(event) => {
                          event.preventDefault();
                          onChange?.(
                            value.filter((_, itemIndex) => itemIndex !== index),
                          );
                        }}
                      >
                        {term}
                      </Tag>
                    ))}
                </Space>
              </div>
            ) : (
              <div>
                {text(
                  value.length ? "blockedTermsNoMatch" : "blockedTermsEmpty",
                )}
              </div>
            )}
            {filtered.length > 50 && (
              <Pagination
                size="small"
                current={currentPage}
                pageSize={50}
                total={filtered.length}
                onChange={setPage}
              />
            )}
            <div className={styles.description}>
              {text("blockedTermsMediaHelp")}
            </div>
          </Space>
        </Modal>
      </>
    );
  }

  function SocialTriggerSettingsPanel() {
    const { t, i18n } = useTranslation();
    const text = (key: string, values?: Record<string, unknown>) =>
      t(`plugins.participation.${key}`, values);
    const [form] = Form.useForm<Values>();
    const [data, setData] = useState<SocialTriggerSettings | null>(null);
    const [scope, setScope] = useState<SocialTriggerScope>("defaults");
    const [kind, setKind] = useState("");
    const [channelId, setChannelId] = useState("");
    const [groupId, setGroupId] = useState("");
    const [agentId, setAgentId] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const [dirty, setDirty] = useState(false);
    const mode = Form.useWatch("mode", form);
    const dryRun = Form.useWatch("dryRun", form);
    const modelEnabled = Form.useWatch("decisionModelEnabled", form);
    const quiet = Form.useWatch(["quietHours", "enabled"], form);
    const automatic =
      mode === "smart" || mode === "probability" || mode === "always";
    const showModelOptions =
      mode === "smart" &&
      modelEnabled &&
      data?.decisionModelSupported &&
      data.decisionModelConfigured !== false;
    const channel = data?.channels.find(
      (item) => item.channelId === channelId && item.channelKind === kind,
    );
    const groups =
      data?.groups.filter(
        (item) => item.channelKind === kind && item.channelId === channelId,
      ) ?? [];
    const group = groups.find(
      (item) =>
        item.groupId === groupId && (!agentId || item.agentId === agentId),
    );
    const selected =
      scope === "defaults"
        ? data?.defaults
        : scope === "channelTypes"
        ? data?.channelTypes.find((item) => item.channelKind === kind)?.settings
        : scope === "channelInstances"
        ? channel?.settings
        : scope === "groupAgents"
        ? group?.agentSettings
        : group?.settings;
    const overrideCount = Object.keys(selected?.overrides ?? {}).length;

    useEffect(() => {
      let active = true;
      pluginsApi
        .getSocialTriggerSettings()
        .then((result) => {
          if (!active) return;
          const selection = restoreSelection(result);
          setScope(selection.scope);
          setKind(selection.kind);
          setChannelId(selection.channelId);
          setGroupId(selection.groupId);
          setAgentId(selection.agentId);
          setData(result);
        })
        .catch((err) => {
          if (active) setError(err instanceof Error ? err.message : "load");
        })
        .finally(() => {
          if (active) setLoading(false);
        });
      return () => {
        active = false;
      };
    }, []);

    useEffect(() => {
      if (!data) return;
      try {
        localStorage.setItem(
          selectionStorageKey,
          JSON.stringify({ scope, kind, channelId, groupId, agentId }),
        );
      } catch {
        // A blocked or full preference store must not prevent policy editing.
      }
    }, [data, scope, kind, channelId, groupId, agentId]);

    useEffect(() => {
      form.resetFields();
      if (data)
        form.setFieldsValue({
          enabled: data.enabled,
          dryRun: data.dryRun,
          ...selected?.policy,
        });
      setDirty(false);
    }, [data, selected, form, scope, kind, channelId, groupId, agentId]);

    const navigate = (change: () => void) => {
      if (dirty)
        Modal.confirm({
          title: text("unsaved"),
          content: text("unsavedHelp"),
          onOk: change,
        });
      else change();
    };
    const chooseChannel = (id: string, nextKind = kind) => {
      const nextGroups =
        data?.groups.filter(
          (item) => item.channelKind === nextKind && item.channelId === id,
        ) ?? [];
      setChannelId(id);
      setGroupId(nextGroups[0]?.groupId ?? "");
      setAgentId(
        nextGroups[0]?.agentId ??
          data?.channels.find(
            (item) => item.channelId === id && item.channelKind === nextKind,
          )?.agentId ??
          "",
      );
    };
    const chooseKind = (next: string) => {
      setKind(next);
      chooseChannel(
        data?.channels.find((item) => item.channelKind === next)?.channelId ??
          "",
        next,
      );
    };

    const save = async (reset = false) => {
      try {
        if (!reset) await form.validateFields();
        const values = form.getFieldsValue(true);
        if (!reset && values.randomDelayMinMs > values.randomDelayMaxMs) {
          message.error(text("delayInvalid"));
          return;
        }
        setSaving(true);
        await pluginsApi.saveSocialTriggerSettings({
          ...(reset ? {} : values),
          ...(!data?.promptSettingsSupported ? { prompts: undefined } : {}),
          channelKind: kind || "qq",
          channelId,
          groupId,
          agentId,
          scope: selected ? scope : "defaults",
          reset,
          ...(!data?.decisionModelSupported
            ? {
                decisionModelEnabled: undefined,
                decisionModelTimeoutMs: undefined,
                decisionModelMaxCallsPerDay: undefined,
              }
            : {}),
        });
        setData(await pluginsApi.getSocialTriggerSettings());
        setDirty(false);
        message.success(text("saved"));
      } catch (err) {
        if (err && typeof err === "object" && "errorFields" in err) return;
        message.error(err instanceof Error ? err.message : text("saveFailed"));
      } finally {
        setSaving(false);
      }
    };

    if (loading) return <Spin />;
    if (error || !data)
      return (
        <Alert
          type="error"
          showIcon
          message={error && error != "load" ? error : text("loadFailed")}
        />
      );
    const label = (name: keyof SocialTriggerPolicy) => text(`fields.${name}`);
    const number = (
      name: keyof SocialTriggerPolicy,
      min: number,
      max: number,
      scale = 1,
      help?: string,
    ) => (
      <Form.Item
        key={name}
        name={name}
        label={label(name)}
        extra={help ? text(help) : undefined}
        rules={[{ required: true }]}
        getValueProps={(value) => ({
          value:
            typeof value === "number"
              ? Number(
                  (value * scale).toFixed(
                    scale === 100 ? 2 : scale < 1 ? 3 : 0,
                  ),
                )
              : value,
        })}
        normalize={(value) =>
          value === null
            ? null
            : scale < 1
            ? Math.round(Number(value) / scale)
            : Number(value) / scale
        }
      >
        <InputNumber
          min={min}
          max={max}
          step={1}
          precision={scale === 100 ? 2 : scale < 1 ? 3 : 0}
          style={{ width: "100%" }}
        />
      </Form.Item>
    );

    return (
      <section className={styles.root} style={{ margin: "24px 0" }}>
        <h4 style={{ margin: "0 0 20px", fontSize: 18, fontWeight: 600 }}>
          {text("title")}
        </h4>
        <Form
          form={form}
          layout="vertical"
          onValuesChange={() => setDirty(true)}
          onFinish={() => void save()}
        >
          <div style={grid}>
            <Form.Item
              name="enabled"
              label={text("enabled")}
              valuePropName="checked"
              extra={text("enabledHelp")}
            >
              <Switch />
            </Form.Item>
            <Form.Item
              name="dryRun"
              label={text("dryRun")}
              valuePropName="checked"
              extra={text("dryRunHelp")}
            >
              <Switch />
            </Form.Item>
          </div>
          {dryRun === false && (
            <Alert
              style={{ marginBottom: 20 }}
              type="warning"
              showIcon
              message={text("liveWarning")}
            />
          )}
          <div style={{ ...grid, marginTop: 12 }}>
            <Form.Item
              className={styles.scope}
              htmlFor="social-trigger-scope"
              label={
                <div className={styles.scopeHeader}>
                  <span>{text("scope")}</span>
                  <Popconfirm
                    title={text("resetConfirm")}
                    onConfirm={() => void save(true)}
                  >
                    <Button
                      size="small"
                      aria-label={
                        scope === "defaults"
                          ? text("resetDefaults")
                          : text("reset")
                      }
                      disabled={!selected || !overrideCount || saving}
                    >
                      {scope === "defaults"
                        ? text("resetDefaults")
                        : text("reset")}
                    </Button>
                  </Popconfirm>
                </div>
              }
              extra={
                <span
                  style={{
                    display: "block",
                    marginTop: 4,
                  }}
                >
                  {text(
                    scope === "defaults"
                      ? "defaultScopeHelp"
                      : "inheritanceHelp",
                  )}
                </span>
              }
            >
              <Select
                id="social-trigger-scope"
                aria-label={text("scope")}
                value={scope}
                options={scopes.map((value) => ({
                  value,
                  label: text(`scopes.${value}`),
                }))}
                onChange={(value) => navigate(() => setScope(value))}
              />
            </Form.Item>
            {scope !== "defaults" && (
              <Form.Item label={text("channelKind")}>
                <Select
                  aria-label={text("channelKind")}
                  value={kind || undefined}
                  options={data.channelTypes.map((item) => ({
                    value: item.channelKind,
                    label: channelLabel(item.channelKind),
                  }))}
                  onChange={(value) => navigate(() => chooseKind(value))}
                />
              </Form.Item>
            )}
            {!["defaults", "channelTypes"].includes(scope) && (
              <Form.Item label={text("channelInstance")}>
                <Select
                  aria-label={text("channelInstance")}
                  value={channelId || undefined}
                  options={data.channels
                    .filter((item) => item.channelKind === kind)
                    .map((item) => ({
                      value: item.channelId,
                      label: item.channelName || item.channelId,
                    }))}
                  onChange={(value) => navigate(() => chooseChannel(value))}
                />
              </Form.Item>
            )}
            {["groups", "groupAgents"].includes(scope) && (
              <Form.Item label={text("group")}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  aria-label={text("group")}
                  value={groupId || undefined}
                  placeholder={text("noGroups")}
                  options={[
                    ...new Map(
                      groups.map((item) => [
                        item.groupId,
                        {
                          value: item.groupId,
                          label: item.groupName
                            ? `${item.groupName}（${item.groupId.slice(-6)}）`
                            : item.groupId.slice(-6),
                        },
                      ]),
                    ).values(),
                  ]}
                  onChange={(value) =>
                    navigate(() => {
                      setGroupId(value);
                      setAgentId(
                        groups.find((item) => item.groupId === value)
                          ?.agentId ?? "",
                      );
                    })
                  }
                />
              </Form.Item>
            )}
            {scope === "groupAgents" && (
              <Form.Item label={text("agent")}>
                <Select
                  aria-label={text("agent")}
                  value={agentId || undefined}
                  options={groups
                    .filter((item) => item.groupId === groupId)
                    .map((item) => ({
                      value: item.agentId,
                      label: item.agentId,
                    }))}
                  onChange={(value) => navigate(() => setAgentId(value))}
                />
              </Form.Item>
            )}
          </div>
          {!selected ? (
            <Alert
              type="info"
              showIcon
              message={text("noGroups")}
              description={text("noGroupsHelp")}
            />
          ) : (
            <>
              {scope === "groups" &&
                group &&
                Object.keys(group.agentSettings.overrides).length > 0 && (
                  <Alert
                    style={{ marginBottom: 16 }}
                    type="info"
                    message={text("agentOverride")}
                    action={
                      <Button
                        size="small"
                        onClick={() => navigate(() => setScope("groupAgents"))}
                      >
                        {text("viewAgent")}
                      </Button>
                    }
                  />
                )}
              {["groups", "groupAgents"].includes(scope) && group && (
                <Space
                  direction="vertical"
                  style={{ width: "100%", marginBottom: 20 }}
                >
                  {!group.channelEnabled && (
                    <Alert
                      type="warning"
                      showIcon
                      message={text("channelDisabled")}
                    />
                  )}
                  {group.channelEnabled &&
                    (!group.groupPolicyEnabled ||
                      group.groupVisibility !== "all") && (
                      <Alert
                        type="warning"
                        showIcon
                        message={
                          group.policyKnown === false
                            ? text("policyUnknown")
                            : text("visibilityWarning")
                        }
                      />
                    )}
                  {!group.channelParticipationEnabled && (
                    <Alert
                      type="warning"
                      showIcon
                      message={text("channelParticipationDisabled")}
                    />
                  )}
                  {group.hostActivation === "always" && (
                    <Alert
                      type="warning"
                      showIcon
                      message={text("nativeAlwaysWarning")}
                    />
                  )}
                  {!group.settings.allowed && (
                    <Alert type="info" showIcon message={text("groupOptIn")} />
                  )}
                </Space>
              )}
              {selected?.policy.blockedTerms !== undefined && (
                <Form.Item
                  name="blockedTerms"
                  label={label("blockedTerms")}
                  extra={text("blockedTermsHelp")}
                >
                  <BlockedTermsEditor />
                </Form.Item>
              )}

              <Form.Item
                name="mode"
                label={label("mode")}
                rules={[{ required: true }]}
              >
                <Select
                  options={[
                    "smart",
                    "probability",
                    "always",
                    "mention_only",
                    "disabled",
                  ].map((value) => ({ value, label: text(`modes.${value}`) }))}
                />
              </Form.Item>
              {mode === "smart" && (
                <>
                  <p
                    className={styles.description}
                    style={{ margin: "-8px 0 16px" }}
                  >
                    {text("smartHelp")}
                  </p>
                  <Form.Item
                    name="decisionModelEnabled"
                    label={label("decisionModelEnabled")}
                    valuePropName="checked"
                    extra={text(
                      !data.decisionModelSupported
                        ? "modelUnsupported"
                        : !modelEnabled
                        ? "modelOffHelp"
                        : data.decisionModelConfigured === false
                        ? "modelUnavailable"
                        : "modelHelp",
                    )}
                  >
                    <Switch disabled={!data.decisionModelSupported} />
                  </Form.Item>
                  {showModelOptions &&
                    number(
                      "decisionModelMaxCallsPerDay",
                      0,
                      100000,
                      1,
                      "modelBudgetHelp",
                    )}
                  {number("smartScoreThreshold", 0, 100, 100)}
                </>
              )}
              {mode === "probability" && (
                <p
                  className={styles.description}
                  style={{ margin: "-8px 0 16px" }}
                >
                  {text("probabilityHelp")}
                </p>
              )}
              {(mode === "smart" || mode === "probability") && (
                <div style={showModelOptions ? grid : undefined}>
                  {number("replyProbability", 0, 100, 100)}
                  {showModelOptions &&
                    number("decisionModelTimeoutMs", 0, 3000)}
                </div>
              )}
              {automatic && (
                <>
                  <h5
                    style={{
                      margin: "24px 0 16px",
                      fontSize: 16,
                      fontWeight: 600,
                      lineHeight: 1.5,
                    }}
                  >
                    {text("frequency")}
                  </h5>
                  {number("cooldownSeconds", 0, 86400)}
                  <div style={grid}>
                    {number(
                      "maxPassiveRepliesPerHour",
                      0,
                      10000,
                      1,
                      "zeroLimit",
                    )}
                    {number(
                      "maxPassiveRepliesPerDay",
                      0,
                      100000,
                      1,
                      "zeroLimit",
                    )}
                  </div>
                  <Form.Item
                    name={["quietHours", "enabled"]}
                    label={text("quiet")}
                    valuePropName="checked"
                    extra={text("timezone", { timezone: data.timezone })}
                  >
                    <Switch />
                  </Form.Item>
                  {quiet && (
                    <div style={grid}>
                      <Form.Item
                        name={["quietHours", "start"]}
                        label={text("quietStart")}
                        rules={[{ required: true }]}
                      >
                        <Input type="time" />
                      </Form.Item>
                      <Form.Item
                        name={["quietHours", "end"]}
                        label={text("quietEnd")}
                        rules={[{ required: true }]}
                      >
                        <Input type="time" />
                      </Form.Item>
                    </div>
                  )}
                </>
              )}
              <Collapse
                style={{ marginBottom: 20 }}
                items={[
                  ...(automatic
                    ? [
                        {
                          key: "context",
                          label: text("context"),
                          children: (
                            <div style={grid}>
                              {number("contextMessages", 0, 100)}
                              {number("contextTtlSeconds", 1, 86400)}
                              {number("debounceMs", 0, 60000)}
                            </div>
                          ),
                        },
                        {
                          key: "advanced",
                          label: text("advanced"),
                          children: (
                            <>
                              <div style={grid}>
                                {number("randomDelayMinMs", 0, 300, 0.001)}
                                {number("randomDelayMaxMs", 0, 300, 0.001)}
                                {number("maxConsecutiveReplies", 1, 100)}
                                {number("maxBotReplyRatio", 0, 100, 100)}
                              </div>
                              <Form.Item
                                name="mentionBypassCooldown"
                                label={label("mentionBypassCooldown")}
                                valuePropName="checked"
                              >
                                <Switch />
                              </Form.Item>
                            </>
                          ),
                        },
                      ]
                    : []),
                  {
                    key: "prompts",
                    label: text("promptsTitle"),
                    children: data.promptSettingsSupported ? (
                      <>
                        <p className={styles.description}>
                          {text("promptsHelp")}
                        </p>
                        {promptKeys.map((key) => {
                          const header = key.endsWith("Header");
                          const maxLength = header ? 200 : 2000;
                          const defaults =
                            data.promptDefaults?.[
                              i18n.resolvedLanguage?.startsWith("zh")
                                ? "zh"
                                : "en"
                            ];
                          const inputId = `social-trigger-prompt-${key}`;
                          return (
                            <div key={key}>
                              <div className={styles.promptHeader}>
                                <label htmlFor={inputId}>
                                  {text(`promptFields.${key}`)}
                                </label>
                                <Button
                                  type="link"
                                  size="small"
                                  className={styles.promptReset}
                                  aria-label={text("promptResetLabel", {
                                    field: text(`promptFields.${key}`),
                                  })}
                                  onClick={() => {
                                    form.setFieldValue(
                                      ["prompts", key],
                                      selected.inheritedPolicy.prompts?.[key] ??
                                        "",
                                    );
                                    setDirty(true);
                                  }}
                                >
                                  {text(
                                    scope === "defaults"
                                      ? "promptResetDefault"
                                      : "promptResetInherited",
                                  )}
                                </Button>
                              </div>
                              <Form.Item
                                name={["prompts", key]}
                                extra={text(
                                  header
                                    ? "promptHeaderHelp"
                                    : "promptBodyHelp",
                                )}
                                normalize={(value: string) => value ?? ""}
                                rules={[
                                  {
                                    max: maxLength,
                                    message: text("promptTooLong", {
                                      count: maxLength,
                                    }),
                                  },
                                  {
                                    validator: (_, value: string) =>
                                      value &&
                                      (value.includes("\0") ||
                                        (header && /[\r\n]/.test(value)))
                                        ? Promise.reject(
                                            new Error(text("promptInvalid")),
                                          )
                                        : Promise.resolve(),
                                  },
                                ]}
                              >
                                {header ? (
                                  <Input
                                    id={inputId}
                                    allowClear
                                    maxLength={maxLength}
                                    placeholder={defaults?.[key]}
                                  />
                                ) : (
                                  <Input.TextArea
                                    id={inputId}
                                    autoSize={{ minRows: 3, maxRows: 10 }}
                                    maxLength={maxLength}
                                    showCount
                                    placeholder={defaults?.[key]}
                                  />
                                )}
                              </Form.Item>
                            </div>
                          );
                        })}
                      </>
                    ) : (
                      <p className={styles.description}>
                        {text("promptsUnsupported")}
                      </p>
                    ),
                  },
                ]}
              />
            </>
          )}
          <Button
            type="primary"
            htmlType="submit"
            loading={saving}
            style={{ marginTop: selected ? 0 : 16 }}
          >
            {text("save")}
          </Button>
        </Form>
        {data.recent && (
          <details style={{ marginTop: 20 }}>
            <summary>{text("recentDecision")}</summary>
            <p>
              {text(`reasons.${data.recent.reasonCode}`, {
                defaultValue: text("unknownDecision"),
              })}
            </p>
          </details>
        )}
      </section>
    );
  }

  return SocialTriggerSettingsPanel;
}
