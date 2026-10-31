# 兼容性与验证范围

当前正式版为 0.3.0，支持符合接口契约的多通道群聊策略、群聊屏蔽词及回复输出过滤。需要配套更新 Fork Octop、octop-gateway 和策略插件；接入 Octo 时还需更新 octop-channel-octo。不能只上传策略 ZIP 后假定旧宿主具备多通道能力。

## 新版所需接口

- Harness：PluginContext.inbound 注册与卸载生命周期。
- Gateway：逐条入站处理器、授权续派发、InboundReceipt、BaseChannel.plugin_group_settings 和 on_inbound_claimed。
- Octop：settings_version=2 的分层设置接口、通配通道设置声明、可选决策评分器注入。
- Octo：可靠成员身份解析及持久收件箱接管回调；成员查询与名称查询共用缓存。

插件加载会检查必要接口；宿主界面遇到旧策略插件会提示更新。插件和通道开关启用时，未纳入群的普通消息及缺少可靠识别信息的消息会跳过；人工 @ 和命令仍遵循通道规则。插件或通道开关关闭后，通道原有触发规则重新生效。

## 0.3.0 的额外要求

群聊静默输出保护需要 Gateway 的 `InboundReceipt.text_filter`、`suppress_thinking` 和 `current_inbound_receipt`；没有这些接口时，插件记录 `output_guard_unavailable` 并跳过实际自动回复，试运行仍可记录决策，人工 @ 继续按旧通道规则处理。Octop 的配套更新会在自动参与时允许专家选择不发言。升级时需要同时更新 Gateway、Octop 和策略插件；Octo 通道建议更新到包含机器人消息过滤的版本。

保护只识别明确的静默标记和部分独立的括号状态或动作，不能保证识别所有模型正文；正常括号内容不会一律删除。自动参与不发送结构化 thinking 或 `<think>` 内容；人工 @ 和其他通道场景仍由 `show_thinking` 控制。

## 验证方法与边界

`make all` 构建插件并运行配套源码测试和原生 ZIP 安装/卸载检查。测试使用隔离的 OCTOP_HOME。脚本默认查找工作区 repos 下的五个仓库，其他布局传入 `--repos-root`。

QQ、Octo 的离线测试覆盖真实 Gateway 处理链、试运行、发送回执、@ 回复、配额和收件箱容量。Discord、飞书、Telegram 补齐公共元数据与设置路径；代码测试不代表各平台已经完成真实机器人联调。平台授权、发送窗口和配额仍由通道执行。

群策略要求全部消息可见范围。QQ 的权限必须在群侧开启；历史收消息故障及实测证据见[排查报告](qq-receive-diagnosis.md)。插件不能读取或代替该平台授权。

## 历史包

patches 目录和[旧验证记录](validation.md)保留 0.1.x 的接入历史，不代表当前兼容要求。host-patches-0.1.x ZIP 缺少新版接口，不能用来升级到 0.3.0；新版构建只产出插件 ZIP 和校验文件。Octop/Gateway 的配套接口尚未进入上游发行版，部署时使用 Fork `develop` 或包含相同能力的兼容构建。

升级和迁移规则见[多通道设置](scoped-settings.md)，降级前先阅读[回滚说明](rollback.md)。
