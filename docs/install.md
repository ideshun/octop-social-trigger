# 安装、升级与灰度

当前正式版为 0.2.0，需配套使用含入站策略接口的 Octop 与 Gateway Fork；使用 Octo 通道时还需更新 `octop-channel-octo` 至 v1.1.0 或兼容版本。多通道能力及继承配置见[多通道设置](scoped-settings.md)。旧 host-patches 包不能升级到多通道能力。

## 宿主兼容要求

完整功能需要 Octop Fork 提供分层设置接口、通道配置声明和可选决策模型注入；Gateway Fork 需要逐条入站策略和 `on_inbound_claimed` 收件箱交接。推荐使用 [ideshun/Octop 的 `develop`](https://github.com/ideshun/Octop/tree/develop) 与 [ideshun/octop-gateway 的 `develop`](https://github.com/ideshun/octop-gateway/tree/develop)。

直接安装 ZIP 不会修改 Octop 宿主。腾讯上游及不含上述接口的旧版宿主不支持完整多通道功能；不要把历史补丁套到不匹配的源码版本。先检查[兼容性说明](compatibility.md)。

## 安装 v0.2.0

固定版本的发布包：[`octop-social-trigger-0.2.0.zip`](https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip)，SHA-256 校验值见发布页提供的 `SHA256SUMS` 文件。

**管理页面**：打开 **管理 → 插件 → 安装**，粘贴上面的 ZIP 下载地址，或先下载 ZIP 再上传。安装完成后启用「群聊自动参与」插件。

**命令行**：

```sh
# 首次安装
octop plugin install https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip

# 覆盖已安装版本
octop plugin install https://github.com/ideshun/octop-social-trigger/releases/download/v0.2.0/octop-social-trigger-0.2.0.zip --force
```

命令也可安装本地插件目录，但不接受本地 ZIP 文件路径。安装目录应在 Octop 服务使用的运行环境中操作。

## 首次启用与试运行

1. 备份 Octop 配置和数据库，确认目标平台和群聊已授权机器人接收普通群消息。
2. 在 Octop 的目标通道设置中开启「群聊自动参与」。这只允许插件处理普通群消息。
3. 在插件设置中启用插件，并只选择要测试的通道和群；保留默认试运行状态。
4. 按群设置为「智能选择」或指定回复概率。检查 `dry_run_would_trigger`、`score_below_threshold` 等决策原因，以及白名单和回复限额。
5. 验证 @ 回复仍按 Octop 原有流程运行。只有确认群范围、平台权限和决策结果后，才关闭试运行；关闭试运行后，符合条件的消息可能触发 Agent 并发送群聊回复。

插件默认 `enabled=false,dryRun=true`。智能模式下决策模型选项默认开启，但只有 Octop 全局模型启用并可用时才调用。试运行也可能把当前消息及最多五条近期群消息发送给配置的决策服务；服务不可用、超时或达到每日限额时会回退本地规则。

## 升级与重载

通过管理页面上传新版本，或使用上面的 CLI 命令并添加 `--force`。升级不会覆盖 `$OCTOP_HOME/plugin-state/octop-social-trigger/` 中的持久配置和状态数据库。

升级后在管理页面点击「重载」，或重启正在运行的 Octop 服务。`octop plugin reload` 只重载执行该命令的离线进程，不会重载后台服务。

## 回滚

在管理页面禁用插件并关闭对应通道的「群聊自动参与」，再安装旧 ZIP。保留 `$OCTOP_HOME/plugin-state/octop-social-trigger/`，避免丢失群策略、去重和配额状态。完整恢复说明见[回滚文档](rollback.md)。

## 更多说明

- [兼容性与验证范围](compatibility.md)
- [QQ 收消息排查](qq-receive-diagnosis.md)
- [状态和验证记录](validation.md)
- [设计文档](octop-social-trigger-design%EF%BC%88Octop%20Social%20Trigger%20%C2%B7%20%E8%AE%BE%E8%AE%A1%E6%96%87%E6%A1%A3%20v1.0%EF%BC%89.md)
