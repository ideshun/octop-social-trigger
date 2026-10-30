# 群聊自动参与插件

让 Octop 根据群聊内容和回复频率，选择性回复普通群消息。机器人被 @ 或收到命令时，仍走 Octop 原有处理流程。

[最新发布：v0.2.0](https://github.com/ideshun/octop-social-trigger/releases/tag/v0.2.0) · [安装包](https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip) · [校验文件](https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/SHA256SUMS)

v0.2.0 支持多通道群聊策略和分层配置。安装前请确认 Octop 与 Gateway 使用包含入站策略接口的配套 Fork `develop`；Octo 通道还需 `octop-channel-octo` v1.1.0 或更新兼容版本。配置层级和平台边界见[多通道设置](docs/scoped-settings.md)与[兼容性说明](docs/compatibility.md)。

## 环境要求

- 0.2.0 需要配套的 [Octop Fork `develop`](https://github.com/ideshun/Octop/tree/develop) 和 [Gateway Fork `develop`](https://github.com/ideshun/octop-gateway/tree/develop)，包含分层设置、通道群聊开关和入站策略接口。使用 Octo 时还需 `octop-channel-octo` v1.1.0 或兼容版本。仅安装本插件不会为旧宿主补上缺失接口。
- 决策模型联动需要 Octop 提供评分器接口，见 [Octop Fork 提交 `dd9dcce8`](https://github.com/ideshun/Octop/commit/dd9dcce8ada359e97d274e0d0c70094a9b908876) 或包含相同能力的兼容版本。
- 对应平台和群聊必须授权并将普通群消息送达 Octop；平台侧权限不由插件配置或绕过。
- 仅安装插件 ZIP 不会为旧版 Octop 增加宿主接口。旧宿主即使能加载插件，也可能没有通道联动或决策模型设置；接入补丁与版本范围见[安装文档](docs/install.md)和[兼容性说明](docs/compatibility.md)。

## 安装

### 通过 Octop 管理页面安装

推荐使用 v0.2.0 固定版本。

1. 打开 **管理 → 插件 → 安装**。
2. 选择一种安装方式：
   - **输入 URL**：粘贴 `https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip` 并安装。
   - **上传 ZIP**：从[发布页](https://github.com/ideshun/octop-social-trigger/releases/tag/v0.2.0)下载 `octop-social-trigger-0.2.0.zip`，然后上传。
3. 安装完成后，在插件列表中启用「群聊自动参与」。升级同 ID 插件时，按界面提示确认覆盖。

### 命令行安装或更新

`octop plugin install` 支持 ZIP URL。已有同 ID 插件时添加 `--force`：

```sh
# 首次安装
octop plugin install https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip

# 更新已安装的插件
octop plugin install https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip --force
```

安装后，使用管理页面中的「重载」让正在运行的 Octop 加载新版本，或重启 Octop 服务。`octop plugin reload` 只重载该 CLI 进程，不会替正在运行的服务重载插件。配置和 SQLite 状态保存在 `$OCTOP_HOME/plugin-state/octop-social-trigger/`，升级会保留这些数据。

## 首次配置

通道开关与插件策略需要同时满足，才会处理普通群消息：

1. 在目标平台和群聊中授权机器人接收普通群消息。
2. 在 Octop 的目标通道设置中开启「群聊自动参与」。
3. 在 **管理 → 插件 → 群聊自动参与** 中启用插件，选择要参与的通道和群。
4. 先保持「试运行」开启，并选择「智能选择」或设置参与概率。试运行只记录决策，不调用 Agent 或发送群回复。
5. 检查决策日志和群范围后，再关闭试运行。关闭后，命中的普通消息会进入 Agent 并可能产生真实 QQ 回复。

新安装时插件默认关闭并处于试运行。常用选项在插件页面配置；高级设置位于 `$OCTOP_HOME/plugin-state/octop-social-trigger/config.json`。插件设置会按所选 QQ 群保存。

## 回复策略

- **仅响应 @**：普通群消息交给 Octop 原有路由。
- **智能选择**：按阈值判断是否参与，再应用参与概率、冷却和回复上限。默认可使用 Octop 的决策模型；模型没有启用、调用失败、超时或达到每日上限时回退到本地规则。
- **按概率参与**：不进行内容评分，直接按配置的概率抽样。
- **每条消息参与**：每条符合范围和安全限制的普通消息都进入回复流程。
- **关闭**：不接管普通群消息。

决策模型选项默认开启，但只有在智能模式下、且 Octop 全局决策模型已启用并可用时才会调用。插件会把当前消息和最多五条近期群消息发送给 Octop 配置的决策服务，每条最多 500 字；试运行也可能调用该服务。默认超时为 1.8 秒、每天最多 100 次。可按群关闭决策模型，或在高级配置中调整 `decisionModelTimeoutMs` 和 `decisionModelMaxCallsPerDay`。

默认智能阈值为 0.7，默认参与概率为 25%。小时/日限额、冷却、连续回复限制、静默时间、群白名单和黑名单仍会限制被动回复。@ 回复和命令保留宿主原有处理方式。

## 常见排查

- **群消息没有进入插件**：确认平台和群侧已授权普通群消息、Octop 通道的消息可见范围允许群消息，并打开对应通道的「群聊自动参与」开关。
- **收到了普通群事件但没有回复**：查看插件设置中的群策略、白名单、试运行状态和 `reasonCode`。`score_below_threshold` 表示评分未达到阈值；`dry_run_would_trigger` 表示试运行判定本可回复，但没有调用 Agent 或发送消息。
- **决策模型没有生效**：确认宿主包含决策模型注入接口，并且 Octop 全局决策模型已启用和配置。不可用时使用本地规则，不影响基本消息处理。

## 高级配置与限制

覆盖顺序为 `defaults` → `channelTypes` → `channelInstances` → `groups` → `groupAgents`。`allowGroups` / `denyGroups` 的每项格式是 `[channelInstanceId, groupId]`，黑名单优先。示例：

```json
{
  "groups": {
    "qq-channel-id": {
      "qq-group-id": {
        "mode": "probability",
        "replyProbability": 0.1,
        "maxPassiveRepliesPerHour": 3
      }
    }
  },
  "allowGroups": [["qq-channel-id", "qq-group-id"]]
}
```

配置和状态使用 `$OCTOP_HOME/plugin-state/octop-social-trigger/`，无需另建数据库。日志记录决策原因和哈希去重键，不记录消息原文。消息只会在启用决策模型时发送到所配置的决策服务；宿主自身日志策略不由插件控制。

v0.2.0 对符合接口契约的通道处理普通群文本。插件不会扩大平台授权范围、绕过平台限制或改变宿主命令鉴权。跨主机共享 SQLite、多进程间完整上下文合并和冷场主动发言不在支持范围内。完整设计见[设计文档](docs/octop-social-trigger-design%EF%BC%88Octop%20Social%20Trigger%20%C2%B7%20%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3%20v1.0%EF%BC%89.md)。

## 开发

需要 Python 3.12+ 和宿主原有开发依赖。核心单测不需要真实机器人凭据：

```sh
python3 -m pytest tests
python3 -m social_trigger check config.example.json
python3 -m social_trigger simulate config.example.json message.example.json
python3 scripts/build.py
```

工作区中运行 `make all` 可构建插件，并用五个配套源码仓库验证接口、测试和原生 ZIP 安装/卸载。其他目录使用 `python3 scripts/verify_compatibility.py --repos-root /五个源码仓库的父目录`；脚本使用隔离数据目录，不会修改运行实例。旧版记录见[验证记录](docs/validation.md)。
