# QQ 群聊自动参与 0.1.2

让机器人根据设定的规则，选择是否参与 QQ 群里的普通聊天，而不是回复每一条消息。群成员 @ 机器人或发送命令时，仍使用 Octop 原来的处理方式。

新安装的插件默认不参与群聊。开启试运行后，插件会判断是否应该回复并记录结果，但不会调用 Agent 或发送普通群消息回复；@ 和命令仍按原来的方式处理。关闭试运行后，符合规则的普通消息才会触发机器人回复。

此前本机测试群已验证普通消息、试运行、@ 回复和一次真实自动回复；测试结束后恢复了试运行。本工作区的新版通道开关和配置界面已做自动化验证，尚未部署到运行中的实例。安装步骤见 [安装文档](docs/install.md) 和 [兼容性说明](docs/compatibility.md)。

先在 QQ 通道的「群聊策略」中允许「QQ 群聊自动参与」，再打开「插件」→「QQ 群聊自动参与」，选择已有 QQ 群并设置参与方式、试运行、概率、回复间隔和上限。群列表来自已有会话；找不到目标群时，先在群里 @ 机器人。群规则按所选群和专家保存，总开关和试运行对插件管理的所有群生效。

## 能力

- 支持仅响应 @、按规则选择参与、按概率参与、每条参与或关闭；新安装默认关闭并启用试运行。
- 全局 → 通道类型 → 通道实例 → 群 → 群内 Agent 的配置覆盖，群白/黑名单。
- SQLite 原子去重、配额预占、小时/日限额、冷却、连续回复限制与最近被动回复占比；共享同一数据库的进程保持配额与去重。
- 单进程多 worker 的群/Agent 隔离防抖合并、TTL、随机延迟；@ 取消待发被动任务，卸载/重载/宿主关闭时取消任务。
- 原生通道权限、命令鉴权、工具上限、发送频控保持生效。v1 接入仅开放 QQ 普通群文本；机器人身份必须来自平台 `author.bot`，缺失时跳过。
- 配置 Schema、生效配置与来源查询、离线模拟、结构化原因日志、配额状态与未知发送恢复命令。

## 开发与验证

核心和本地命令仅使用 Python 标准库。宿主及其回归测试需要宿主原有开发依赖和 Python 3.12+。

```bash
python3 -m social_trigger check config.example.json
python3 -m social_trigger check config.example.json --scope qq channel-id group-id agent-id
python3 -m social_trigger simulate config.example.json message.example.json
python scripts/build.py
python scripts/verify_compatibility.py --repos-root /path/to/clean/repositories
```

兼容性脚本要求指向未应用补丁的基线源码，在临时目录复制三个宿主源码包，核对补丁基线、应用补丁、运行离线集成/回归、测试原生 ZIP 安装器；不修改宿主工作树、运行实例或频道配置。独立 `unittest` 在未打宿主补丁时会明确跳过接入测试，不能用跳过结果声称通过端到端验收。

安装和回退见 [安装文档](docs/install.md)、[回滚文档](docs/rollback.md)。产物为 `dist/octop-social-trigger-0.1.2.zip`，旧版宿主补丁单独打包，校验值在 `dist/SHA256SUMS`。

## 配置语义

覆盖顺序：`defaults` → `channelTypes[platform]` → `channelInstances[instanceId]` → `groups[instanceId][groupId]` → `groupAgents[instanceId][groupId][agentId]`。标识符必须为稳定 ID；不同实例的同名群不共享配置。`allowGroups` / `denyGroups` 的每项为 `[instanceId, groupId]`；空白名单表示不限制，黑名单优先。

```json
{
  "groups": {"channel-id": {"group-id": {"mode": "probability", "replyProbability": 0.1}}},
  "groupAgents": {"channel-id": {"group-id": {"agent-id": {"maxPassiveRepliesPerHour": 3}}}},
  "allowGroups": [["channel-id", "group-id"]]
}
```

QQ 通道的「QQ 群聊自动参与」开关仅决定插件是否可以处理该通道，不会替代插件的启用和试运行设置；关闭通道开关、`enabled=false` 或 `mode=disabled` 时交还宿主原有路由；宿主若设为 `activation=always`，禁用插件后仍会原生逐条触发。建议以 `activation=mention` 作为回退基线。`enabled=true,dryRun=true` 接管普通群文本，符合触发条件也只返回 `skip/dry_run_would_trigger`，不调用 Agent；@ 和命令保留原有流程。在插件管理界面保存时立即生效；直接修改配置文件后需在管理员页面重载插件或重启宿主。

`visibility=all` 在宿主和 QQ 群侧都要授权；配置不能让平台推送原本无权读取的消息。没有可靠机器人身份、Agent ID 或全量事件时，普通消息安全跳过。`mentionBypassCooldown=false` 可使 @ 遵循插件冷却，其余配额只针对被动回复；状态故障时 @ 回退宿主。

`smart` 默认可使用 Octop 已启用的决策模型，判断是否适合参与；插件的 `decisionModelEnabled` 可按群关闭，未启用全局决策模型、宿主不支持、请求失败或超时时回退到本地规则。调用可能将当前和最多五条近期群消息发送给配置的决策服务，每条最多 500 字；服务可能位于远端。决策调用在冷却、配额等基础限制之后进行，默认超时 1800 毫秒（最高 3000）、每日最多 100 次，可在高级配置中用 `decisionModelTimeoutMs`、`decisionModelMaxCallsPerDay` 调整；达到上限也回退规则。试运行不调用主 Agent 或发送消息，但启用的决策模型仍可能被调用。

本地规则评分：回复机器人 0.7、问句 0.3、近期话题词重合 0.35、至少三条且两名成员的活跃讨论 0.15，总分不超过 1；模型或规则评分达到阈值后才按 `replyProbability` 抽样。v1 QQ 不猜测未知引用目标，因此回复机器人信号仅在宿主明确提供时有效。旧配置的 `classifier` 字段保留以兼容历史版本，不控制决策模型开关。

小时限额为滚动 3600 秒，每日按配置的 IANA 时区；0 配额表示禁止被动回复。连续回复在新的真人消息时间晚于上次发送时归零。`maxBotReplyRatio` 统计 TTL 内本插件的成功被动回复占已观察真人被动消息与这些回复之和的比例；不统计其他机器人或插件以外的主动输出。`quietHours` 支持跨午夜，起止相同表示全天静默。

## 状态与限制

配置/状态使用 `$OCTOP_HOME/plugin-state/octop-social-trigger/`，没有独立数据库服务。默认日志仅记录原因、哈希去重键和预占 ID，不写消息原文；宿主自身已有日志策略不由本插件改写。

```bash
python3 -m social_trigger status config.json /path/to/state.db
python3 -m social_trigger resolve config.json /path/to/state.db RESERVATION_ID --outcome sent
python3 -m social_trigger resolve config.json /path/to/state.db RESERVATION_ID --outcome not_sent
```

发送结果不明（例如传输超时）时保留 pending 并阻止该作用域继续被动触发。只有核实平台结果后才能手动解决；不自动重发。完全未尝试发送的取消会释放配额，任何成功可见输出（含宿主错误提示）都消耗一次被动回复名额。

- v1 的实际接入限定 QQ 群普通文本；其他通道的被动输入默认跳过，@ 保留宿主行为；可用该通道 `mode=disabled` 交还原路由。
- 内存合并/上下文只保证一个宿主进程内协调；多进程共享 SQLite 只保证去重/预占/配额，不保证跨进程完整合并；不支持跨主机共享 SQLite。
- 无原生消息 ID 时使用内容哈希加 10 秒时间桶有限去重；不能保证绝对准确。去重保留 24 小时。
- 不开放旧 `classifier` 配置和冷场主动发言。管理页提供常用群设置，其他高级规则仍使用配置文件。
- 关闭时已经在平台执行但结果不明的发送无法撤回；该场景保守留存 pending。
