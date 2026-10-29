# Octop Social Trigger — 通用群聊智能参与插件设计文档

> 状态：可交付 Codex 的实施规格（v1.0）  
> 日期：2026-10-29  
> 目标平台：TencentCloud/Octop + TencentCloud/octop-gateway  
> 默认时区：`Asia/Shanghai`（UTC+08:00）  
> 仓库建议名：`octop-social-trigger`  
> 核心原则：**插件负责决定“是否、何时、以什么频率唤醒 Agent”；Agent 自己决定“回复什么”。**

## 0. 交给 Codex 的执行指令（先读）

请按本设计文档直接开发可发布的通用 Octop 插件，不要把插件与任何固定 Agent 名称、人格或模型绑定。先检查当前 Octop / octop-gateway 代码和插件 API，记录版本/commit 与实际可用的消息入口扩展点，然后实现代码、测试、配置示例、安装文档和可安装 ZIP。**不要假定现有 `hook` 能截获未触发的群消息**；如果缺少入站 pre-dispatch hook，应先设计最小兼容扩展，再将独立策略引擎注册进去。所有实现必须可测试、可关闭、可回滚。不允许通过让 Agent 每条群消息先生成答案、再删除答案的方式模拟选择性回复。

完成后输出：
1. 代码仓库及目录说明；
2. Octop 原生插件 ZIP 和 SHA-256；
3. 必要时单独提交的最小 Gateway/Octop 兼容补丁及其 PR/应用说明；
4. 配置示例及安装/卸载/回滚步骤；
5. 自动化测试结果和人工验收记录；
6. 无法由当前官方 API 完成的功能清单与客观限制。

## 1. 背景与目标

当前 Octop 的群聊策略已经可以区分消息可见范围与触发方式，但默认触发方式偏向被 @ 后才响应。目标是增加一个**可配置的选择性群聊参与层**，使 Agent 不必每条消息必回，也不必每次都被 @ 才能介入。

### 1.1 目标

- 对 QQ、Telegram、Discord 等**具备合法消息可见权限**的群聊渠道使用同一套决策核心；第一版以 QQ 联调，通道适配能力逐一检测，而非承诺所有通道都能读取非 @ 消息。
- 支持全局默认策略，按通道实例、群、Agent 覆盖配置；同一插件可服务任意多个专家。
- 支持 `mention_only`、`smart`、`probability`、`always`、`disabled` 模式。
- 支持每小时/每日限额、冷却、随机延迟、连续发言上限、消息防抖合并、上下文 TTL、静默时间段、分群控制。
- 智能模式先做零/低成本规则筛选，必要时使用可选的轻量分类器，只有决定回复后才调用主 Agent。
- 真正“跳过”：不运行主 Agent、不发送占位文字、不产生“SKIP”或空消息。
- 提供结构化原因日志、模拟测试和开关回退；稳定后发布为可安装插件。

### 1.2 非目标

- 不内置人格、昵称、语气风格、改写器、Humanizer、李白等写作 Skill。
- 不改动 Agent 的系统提示词、长期记忆、技能/工具权限或安全策略。
- v1 不做复杂的群成员画像、关系图、自动发梗/发图，也不将“群聊冷场主动发言”列为必须交付项。
- 不以非官方 QQ 协议绕过平台可见范围或主动消息限制。
- 不对私聊、命令、管理指令应用群聊随机回复规则。

## 2. 已确认的 Octop 技术事实与待验证点

### 2.1 官方确认

- Octop 插件类型包含 `tool` / `skill` / `hook`，使用 `plugin.yaml` + `main.py`，入口为 `setup(ctx)`；`hook` 示例通过 `ctx.middleware(...)` 注册 **AgentMiddleware**，主要围绕模型调用前后运行。
- `octop-gateway` 使用 `InboundMessage`、`ChannelSubject` 和 `MessageProcessor`，统一输入输出并管理各通道。
- Gateway 的 `group_context` 明确区分：`visibility`（`auto` / `all` / `mention_recent` / `mention_only`）、`activation`（`mention` / `always`）、历史记录与 TTL；`always` 仅在显式 `all` 可见时允许。
- 官方插件 ZIP 需要恰好一层含 `plugin.yaml` 的根目录；安装命令可使用 `octop plugin install <路径> --force`，插件热加载有 `octop plugin reload`。

### 2.2 严格待验证

1. 当前用户实际安装的 Octop / octop-gateway 版本、源代码 commit、依赖关系。
2. 在消息被 `activation=mention` 拦截前，有无**官方支持**的入站监听或 pre-dispatch 扩展点。
3. 通道消息是否包含可靠的 `message_id`、群 ID、发送者 ID、@ 标记、回复目标、通道实例 ID；缺失时降级策略是什么。
4. 发送前是否有官方中断/延时/主动发送接口；插件能否取消 pending 回复。
5. 插件设置在 Dashboard 管理页的真实扩展能力；**官方示例中的 `ui/` 是工具结果卡片 UI，不可直接视为通用配置页面扩展机制。**
6. QQ 官方通道实际下发的消息范围、主动回复窗口及频率限制。

> **阻塞规则：** 如果消息在进入插件之前已经被平台或 Gateway 丢弃，插件不可能通过提示词恢复未接收到的消息。不得假造此功能已实现。

## 3. 设计原则与技术约束

1. **人格隔离**：不读取和改写专家人格；专家只接收被批准的对话上下文。
2. **配置驱动**：全局默认 → 通道类型 → 通道实例 → 群 → 群内 Agent（越具体优先级越高）。禁止以专家名字、昵称等不稳定字符串为键，应使用稳定 `agent_id`。
3. **防刷屏优先**：安全与渠道权限 > 过滤/禁用 > 冷却与限额 > 提及优先规则 > 智能判断 > 生成回复。
4. **真实前置判断**：所有不参与判定应发生在主 Agent 开始推理之前。
5. **最小侵入**：插件内保留平台无关的核心规则，Gateway 适配层尽可能薄；新增接口须能禁用。
6. **失败安全**：非 @ 消息在状态存储、分类器或适配器异常时默认跳过；被 @ 的消息回退到官方原有流程，但仍受平台权限和安全策略约束。
7. **隐私与合规**：只保留必要上下文，按群隔离，不记录无必要的原文到持久日志；消息权限降级时清除缓存。
8. **默认保守**：安装后 `enabled=false` 或 `dry_run=true`；未显式授权 `visibility=all` 的群不得启用非 @ 模式。

## 4. 总体架构

```text
已授权的 QQ / Telegram / Discord 等通道
                │
         InboundMessage
                │
     ┌──────────▼──────────┐
     │ Gateway 规范化与权限层 │ ← 官方平台限制
     └──────────┬──────────┘
                │
     ┌──────────▼──────────┐
     │ 入站 pre-dispatch    │ ← 优先复用官方接口；缺失则做最小补丁
     └──────────┬──────────┘
                │
     ┌──────────▼──────────┐
     │ Social Trigger Core │
     │  过滤/去重/限流       │
     │  消息合并/话题判断     │
     │  冷却/静默/抽样       │
     └──────┬───────┬──────┘
            │       │
         SKIP     TRIGGER / DELAY
            │       │
         终止      ▼
                原生 Agent 执行
                    │
                原生通道发送
```

### 4.1 分层职责

- **Core**：纯逻辑 `evaluate(message, context, effectiveConfig, state) -> Decision`；不依赖 QQ，也不依赖具体 Agent。
- **State Store**：按 `channel_instance_id + group_id + agent_id` 隔离缓存、频率计数、去重记录、发言状态；v1 可采用 Octop 原有存储设施，不为这点功能新增 Redis 等独立服务。
- **Gateway Adapter**：把真实消息规范化、调用 Core、在合适时机继续/取消/延迟 Agent 调用；必须明确时序和异常回退。
- **Optional Classifier**：只负责“是否值得参与”，不生成内容；缺省规则模式可以独立运行。
- **Config Surface**：v1 至少提供经过 Schema 校验的配置文件和管理员可检查的生效配置；Dashboard 可视化配置作为后续增强。

### 4.2 插件交付形态

优先方案 A：现有 Host/Gateway 暴露合适的入站扩展点 → 打包纯独立 `kind=hook` 插件（具体注册方式以源码为准）。

备选方案 B：无此扩展点 → 在 Octop/Gateway 增加 **最小的、向后兼容的消息决策 Hook 接口**，再由独立插件注册处理器。补丁必须单独提交、可测试、可回滚；禁止修改第三方依赖安装目录或 monkey-patch 私有方法作为最终发布方案。

如果当前 Octop PluginContext 无法承载该扩展，也不能通过正式注册接口生效：**须明确标为“需要宿主版本支持”**，不得把只有模型中间件的代码包装成“完整通用群聊触发插件”。

## 5. 规范化输入与决策输出

以下为**跨语言契约示例（TypeScript 类型定义，非 Octop 已存在 API）**；后端按官方要求以 Python 实现等价数据模型，注意类型与字段均需通过真实源码适配：

```ts
export type ReplyMode = 'disabled' | 'mention_only' | 'smart' | 'probability' | 'always';
export type DecisionType = 'skip' | 'trigger' | 'delay';

export interface GroupMessage {
  platform: string;
  channelInstanceId: string;
  groupId: string;
  agentId: string;
  messageId: string;
  senderId: string;
  text: string;
  receivedAt: string;
  isMentioned: boolean;
  isReplyToBot: boolean;
  isBotMessage: boolean;
  isCommand: boolean;
  visibilityGranted: 'all' | 'limited' | 'unknown';
}

export interface TriggerDecision {
  action: DecisionType;
  reasonCode: string;
  delayMs?: number;
  evaluatedScore?: number;
  dedupeKey: string;
}
```

### 5.1 决策规则（按顺序）

1. 若全局/群/Agent 禁用：跳过，**不改动宿主既有 @ 路由**（配置 `disabled` 的准确含义需明确定义并在 UI 显示）。
2. 验证平台可见权限、群范围和 Agent 权限；对未授权的非 @ 消息跳过。
3. 排除机器人自己的消息、来自其他机器人的回环、Slash 命令/管理事件、重复消息和非群聊消息。
4. 被 @：遵循已有的官方正常回复路径；可选择 `mentionBypassCooldown=true`，但绝不绕过渠道安全/发送频率限制。
5. 非 @：检查静默时段、冷却、小时/日配额、连续发言上限、机器人最近发言占比。
6. 消息合并窗口结束后，用最新的群聊上下文执行 `mode` 策略。
7. `mention_only` → 跳过；`always` → 在限额内触发；`probability` → 按设置的概率抽样；`smart` → 根据上下文相关度/话题热度/与机器人的互动信号评分，达到阈值后再按可配置的概率上限抽样。
8. 判定 `trigger` 后原子化预占配额，进入原生 Agent 执行；在真正成功发送时更新发言状态；取消/发送失败则释放或按明确策略补偿预占。

**特殊说明：** `smart` 的“参与概率上限”不是单纯固定的随机回复概率；先满足相关性门槛，再抽样。支持 `dry_run` 输出原因但不实际发送。

### 5.2 消息合并

- 默认 `debounce_ms=1500`，在同一群同一 Agent 的窗口内合并连续消息，窗口到期只做一次决策。
- 被 @ 消息应优先触发并结束/复用现有合并窗口，防止重复回答。
- 同群多消息异步到达时，不允许跨群串话、死锁、乱序重复触发。
- 合并仅存短期消息内容，不改变 Octop 原生聊天历史本身。

### 5.3 模型可选判断

- 默认 `classifier.enabled=false`，先用规则与主题信号完成 MVP。
- 开启时独立使用用户已有的合规轻量模型配置或宿主允许的模型路由；只读取允许范围内的最近消息。
- 分类器输出固定 Schema：`participate:boolean`、`confidence:0..1`、`reason_code:string`，不接受任意可执行文本。
- 设置最大超时、次数与每日 Token 上限；超时/非法输出/限额超出时 `skip`；不能阻塞其他群。
- 不将“如何回复”“改变人格”等指令交给分类器。

## 6. 完整配置契约（目标 Schema，非官方现成字段）

```json
{
  "enabled": true,
  "dryRun": true,
  "timezone": "Asia/Shanghai",
  "defaults": {
    "mode": "smart",
    "visibilityRequired": "all",
    "replyProbability": 0.25,
    "smartScoreThreshold": 0.7,
    "cooldownSeconds": 180,
    "maxPassiveRepliesPerHour": 8,
    "maxPassiveRepliesPerDay": 30,
    "maxConsecutiveReplies": 2,
    "randomDelayMinMs": 1000,
    "randomDelayMaxMs": 5000,
    "debounceMs": 1500,
    "contextMessages": 20,
    "contextTtlSeconds": 600,
    "mentionBypassCooldown": true,
    "quietHours": {
      "enabled": false,
      "start": "23:00",
      "end": "08:00"
    },
    "classifier": {
      "enabled": false,
      "timeoutMs": 1800,
      "maxCallsPerDay": 100
    }
  },
  "channelTypes": {},
  "channelInstances": {},
  "groups": {},
  "groupAgents": {},
  "allowGroups": [],
  "denyGroups": []
}
```

说明：

- `channelTypes` / `channelInstances` / `groups` / `groupAgents` 是覆盖表；精确键使用稳定 ID，不能仅按群昵称定位。需要提供严格定义和示例。
- `replyProbability`：`probability` 模式下为触发概率，`smart` 模式下为最高抽样概率；0 表示只保留 @ 路径。
- 所有数值都应有范围校验、默认值和错误提示。非法配置不能静默变成“全部消息都回复”。
- `quietHours` 支持跨午夜且使用 IANA 时区，不依赖服务器所在时区。
- 显示实际生效配置并标注来源（全局、通道、群、Agent），敏感内容不出现在日志中。
- 当 `visibilityRequired=all` 但真实权限不满足时，强制降级到被 @ 模式并提示。
- v1 管理工具修改通道配置时应避免覆盖已有凭据；优先使用安全的部分更新/读改写和备份，不将凭据输出到日志。

## 7. 状态管理与防刷屏

### 7.1 状态隔离

状态键：`tenant/user scope + channelInstanceId + groupId + agentId`。如果宿主不支持租户字段，则用宿主实际访问控制范围作为隔离边界。

建议维护：消息去重索引、当前窗口消息、最近非 @ 回复时间、小时/日计数、连续回复计数、最近机器人的发言、静默到期时间。计数以真实发送成功为主，但在并发处理阶段必须使用原子预占确保配额不被突破。

### 7.2 并发/持久化

- 每群每 Agent 使用局部异步锁或等价轻量机制；不同群互不阻塞。
- 基于 `messageId` 实现幂等；若平台不提供可靠 ID，使用小窗口 hash 作为**有限的降级去重**并记录指标，不能承诺绝对准确。
- 多 worker / 重启要明确共享存储边界；小时/日限额不可因重启无限重置。首版尽量复用 Octop 存储，不能保证则明确范围并增加集成测试。
- 关闭/卸载插件时清理未发送的延迟任务；恢复官方原有逻辑。
- 不用未被授权的历史消息生成回复，不存储超过 `contextTtlSeconds` 的被动上下文。

## 8. 配置界面与可观测性

### 8.1 首版配置（P0 必须）

- 可审阅的 JSON 配置 + Schema 校验 + 运行状态展示 + dry-run 开关。
- 对管理员展示：是否启用、匹配的群/Agent、真实群消息可见性、触发模式、冷却/配额、最近一次跳过原因。
- 至少提供“检查配置”和“模拟输入后返回决策”的本地命令或测试工具。

### 8.2 Dashboard UI（P1，推荐）

React + TypeScript：全局设置页、通道实例设置、群设置、Agent 覆盖、模拟器、最近决策记录。

注意：官方演示的 `ui/dist/index.js` 用于渲染**工具结果卡片**，不是已确认的管理页面插槽。实现前必须查清真实 Dashboard 插件管理页和 API 是否允许增加设置表单；不支持时先提供配置文件/管理 API，UI 单独扩展，不得虚构设置页面能力。

### 8.3 结构化日志

建议事件：`message_seen`、`decision_skip`、`decision_trigger`、`reply_sent`、`reply_failed`、`rate_limited`、`permission_downgraded`、`classifier_failed`。包含安全的 ID、时间、`reasonCode`、耗时、配额消耗；默认不写消息明文、用户隐私或 API Token。

## 9. 交付范围与阶段

### P0 — 可用 MVP（首要验收）

- [ ] 构建独立决策核心、配置 Schema、单元测试。
- [ ] 实现群消息标准化适配：先在 QQ 群验证实际消息可见性。
- [ ] 在**主 Agent 推理之前**实现 `skip/trigger/delay`；明确 Gateway 接入方式。
- [ ] 支持 @ 优先、`mention_only`、`probability`、`smart`（规则评分）、`always`。
- [ ] 实现冷却、小时/日限额、连续回复、消息合并、随机延时、静默时段。
- [ ] 支持全局 + 通道实例 + 群 + Agent 覆盖；状态隔离与去重。
- [ ] 干运行、日志、配置检测、安装/卸载/回退。
- [ ] 官方插件标准 ZIP；若必须修改 Gateway，单独交付兼容补丁。

### P1 — 体验增强

- [ ] React + TypeScript 管理界面（取决于真实可扩展性）。
- [ ] 可选轻量分类器与分类预算。
- [ ] 决策模拟器、指标统计、群级调参。
- [ ] 适配其他允许接收非 @ 群消息的官方通道。

### P2 — 高级参与（必须单独获得平台能力确认）

- [ ] 群聊冷场后可选主动发言/分享话题。
- [ ] 细粒度社交信号、成员偏好（需隐私和数据生命周期设计）。
- [ ] 可选内容禁忌与话题黑白名单，但不越权覆盖 Agent 安全规则。

## 10. 验收测试矩阵

| 用例 | 预期 |
| --- | --- |
| 被 @，非 @ 模式关闭 | 仍走原有正常回复路径；不受非 @ 冷却影响 |
| 非 @ 且群消息可见权限不足 | 不触发 Agent；显示权限降级原因 |
| `mention_only` | 非 @ 消息全部跳过，无主 Agent Token 消耗 |
| `probability=0` | 非 @ 触发次数为 0 |
| `probability=1` + 无限制 | 所有符合过滤条件的非 @ 消息进入 Agent |
| `smart` 低相关性 | 可解释地跳过；不产生主 Agent 响应 |
| 1 秒内连发 5 条消息 | 在防抖窗口按配置合并，最多触发一次 |
| 连续机器人输出达到上限 | 非 @ 消息暂时跳过 |
| 命中每小时/日上限 | 严格禁止额外被动回复，支持跨重启验证 |
| 静默 23:00～08:00 | 使用 `Asia/Shanghai`，跨午夜正确，@ 路径按策略保留 |
| 双 worker 同时处理相同 ID | 不重复回复，配额不超发 |
| 平台重投同一 messageId | 去重生效 |
| 分类器超时、存储异常 | 非 @ 安全跳过；无后台大量重试 |
| 平台消息权限被撤销 | 清除无权缓存，拒绝非 @ 回复 |
| 插件禁用/卸载 | 不继续发送延迟消息，Octop 原有机制恢复 |
| 两个 Agent、两个群 | 状态与配置严格隔离，彼此无污染 |
| dry-run 模式 | 记录判定但不发消息、不调用主 Agent |
| 非法配置/群 ID 不匹配 | 报明确错误，绝不悄悄切换 `always` |

**质量门槛**：单测覆盖核心决策分支和边界条件；集成测试需要真实的通道事件仿真；至少一轮实际 QQ 测试群验证消息收取、触发和回复过程。`make all` 或相应官方测试命令必须通过；报告测试数量、失败项和剩余风险。

## 11. 推荐仓库结构（可按现有 API 简化）

```text
octop-social-trigger/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── plugin.yaml
├── main.py                  # Octop 原生插件入口，具体注册方式以实测为准
├── config.example.json
├── pyproject.toml
├── social_trigger/
│   ├── config.py
│   ├── decisions.py
│   ├── rules.py
│   ├── scorer.py
│   ├── state.py
│   └── adapters/
│       └── octop.py
├── tests/
│   ├── test_rules.py
│   ├── test_concurrency.py
│   ├── test_permissions.py
│   ├── test_config.py
│   └── test_gateway_integration.py
├── docs/
│   ├── architecture.md
│   ├── compatibility.md
│   ├── install.md
│   ├── rollback.md
│   └── codex-implementation-notes.md
├── patches/                # 仅在确实必要时：宿主最小兼容补丁
└── ui/                     # P1，且确认官方可嵌入配置管理页后再实现
    └── src/
```

> 原则：不为简单规则引入数据库服务、消息队列服务、重型工作流引擎。优先复用 Octop 原生基础设施。

## 12. 安装、发布与回滚

1. 记录并确认宿主支持的 Octop、octop-gateway 版本矩阵；发布包需要写清最低版本和兼容补丁依赖。
2. 使用官方 `plugin.yaml` 格式，`kind`/`entry` 与当前 `PluginContext` 一致。不能把“自定义 pre-dispatch Hook”伪装成已有 `ctx.middleware()` 能力。
3. 生成只包含一个插件根目录的 ZIP；发布 SHA-256 校验值。
4. 验证命令：`octop plugin install ./octop-social-trigger.zip --force`，`octop plugin list`，`octop plugin reload`；再到插件管理页启用。某些宿主变更可能需要重启，按真实表现写文档。
5. 在测试群开启 `dryRun=true` → 验证权限和日志 → 小比例开启 → 扩大范围。
6. 回滚顺序：停止新触发与延迟发送 → 禁用插件 → 恢复原 `group_context` 配置 → 如需回滚宿主补丁则使用对应版本；确保不影响 QQ 正常被 @ 回复。
7. 不在安装/回滚脚本中重写频道密钥、AppSecret 或现有完整通道配置；更新前备份并核验。

## 13. 风险与不能妥协的约束

- **群消息权限不是提示词权限**：插件无法获取平台未授权推送的消息；不能通过 `visibility=all` 声称权限已自动获取。
- **不能用模型“思考后不回复”代替前置拦截**：那会消耗 Token，且可能形成空消息/额外通知。
- **不能监听到群聊就随意主动推送**：主动发言能力必须遵守通道平台 API 条件及发送窗口。
- **不能对所有插件用户默认开启**：默认静默、用户可控制，可按群停用。
- **不改人格/记忆**：插件要通用，应当独立于 Q 宝、大肥鱼及任何其他专家。
- **不绕过 Octop 宿主的安全控制与命令鉴权**：非 @ 随机参与仅针对普通群聊文本。

## 14. 参考源码（截至 2026-10-29 查询）

1. Octop 主仓库：<https://github.com/TencentCloud/Octop>
2. Octop 插件示例说明：<https://github.com/TencentCloud/Octop/blob/main/plugins/README_CN.md>
3. 原生 `hook` 示例：<https://github.com/TencentCloud/Octop/tree/main/plugins/demo-turn-logger>
4. Octop CLI：<https://github.com/TencentCloud/Octop/blob/main/docs/cli.md>
5. Gateway：<https://github.com/TencentCloud/octop-gateway>
6. Octop 架构：<https://github.com/TencentCloud/Octop/blob/main/docs/architecture.md>
7. Octop Issue（通道配置更新需防整体覆盖）：<https://github.com/TencentCloud/Octop/issues/1190>

以上链接用于开发时对照当时的真实源码。**Codex 必须以实际安装版本和本地仓库实现为准，不直接照抄示例接口或未经证实的配置字段。**

---

## 15. Codex 最终交付定义（DoD）

- [ ] 插件对所有 Agent 通用，不存在固定专家 ID、昵称、人格和供应商硬编码。
- [ ] 至少在 QQ 测试群实现非 @ 选择性触发，并证明判断发生在主 Agent 调用前。
- [ ] 所有配置有默认值、边界校验、作用域合并与 dry-run 行为。
- [ ] 频率/延时/限额/静默/去重/并发测试通过。
- [ ] 明确区分「原生插件可做」「宿主补丁可做」「平台权限无法做」三类能力。
- [ ] 提供可安装 ZIP、完整源码、测试、配置与发布/回滚文档。
- [ ] 安装插件前后原有 `mention` 处理与命令权限保持可用。
- [ ] 不把尚未实现的配置 UI 或主动发言功能写成已完成。

**实施优先级：正确接入消息入口 > 判断与限频正确 > 可安装可回滚 > 可观测 > UI 与增强功能。**
