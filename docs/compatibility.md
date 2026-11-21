# 兼容性与验证范围

当前版本为 0.4.1，支持符合接口契约的多通道群聊策略、群聊屏蔽词、回复输出过滤，并按通道提供的提及元数据拦截只 @ 他人的群消息。需要配套更新 Fork Octop、octop-gateway 和策略插件；接入 Octo 时还需更新 octop-channel-octo。Gateway 适配器必须提供 `bot_mentioned` 和 `has_mentions`，否则插件无法区分普通消息与只 @ 他人的消息。不能只上传策略 ZIP 后假定旧宿主具备多通道能力。

## 新版所需接口

- Harness：PluginContext.inbound 注册与卸载生命周期、ctx.settings(provider)、可选同步 InboundTextRenderer。
- Gateway：逐条入站处理器、授权续派发、InboundReceipt（含 text_filter_finish）、BaseChannel.plugin_group_settings 和 on_inbound_claimed。
- Octop：settings_ui 版本1界面桥接、通用 GET/PUT /api/plugins/{plugin_id}/settings、通道/群目录、入站文本渲染接线、通道设置声明及可选决策评分器注入；插件 settings_version=3。
- Octo：可靠成员身份解析及持久收件箱接管回调；成员查询与名称查询共用缓存。

插件加载会检查必要接口；宿主界面遇到旧策略插件会提示更新。插件和通道开关启用时，未纳入群的普通消息及缺少可靠识别信息的消息会跳过；人工 @ 和命令仍遵循通道规则。插件或通道开关关闭后，通道原有触发规则重新生效。

## v0.4.x 的配套源码

上述通用扩展尚未进入公开 SDK 发行版，普通 Fork develop 也可能缺少接口。不能只上传本插件 ZIP；旧宿主请继续使用 v0.3.3。先升级并核验接口，再安装插件。没有编造最低发行版本号。

已公开的通用扩展源码参考（这些 PR 尚未合并，不代表上游已正式支持）：

- [Harness #177](https://github.com/TencentCloud/octop-harness/pull/177)，提交 [`bc32784`](https://github.com/ideshun/octop-harness/commit/bc3278403cbda1a7af475253f8e7942a58b5f272)。
- [Octop #2620](https://github.com/TencentCloud/Octop/pull/2620)，提交 [`b8fe98b6`](https://github.com/ideshun/Octop/commit/b8fe98b62845582555a2483e52093142d4776804)。
- [Gateway #49](https://github.com/TencentCloud/octop-gateway/pull/49)，提交 [`6f80d24`](https://github.com/ideshun/octop-gateway/commit/6f80d2486f92c38484f62e0629cfee02545b7877)。

这些是接口来源，不是已发布的完整多通道 Fork 发行包；需要把接口整合到兼容基线或使用已验证的工作区源码。插件发布不隐含 Octop/SDK 发版。安装前运行 `scripts/verify_compatibility.py --repos-root ...` 验证目标五仓源码与本插件 ZIP。

## 0.3.0 的额外要求

群聊静默输出保护需要 Gateway 的 `InboundReceipt.text_filter`、`suppress_thinking` 和 `current_inbound_receipt`；没有这些接口时，插件记录 `output_guard_unavailable` 并跳过实际自动回复，试运行仍可记录决策，人工 @ 继续按旧通道规则处理。Octop 的配套更新会在自动参与时允许专家选择不发言。升级时需要同时更新 Gateway、Octop 和策略插件；Octo 通道建议更新到包含机器人消息过滤的版本。

保护只识别明确的静默标记和部分独立的括号状态或动作，不能保证识别所有模型正文；正常括号内容不会一律删除。自动参与不发送结构化 thinking 或 `<think>` 内容；人工 @ 和其他通道场景仍由 `show_thinking` 控制。

## 验证方法与边界

`make all` 构建插件并运行配套源码测试和原生 ZIP 安装/卸载检查。测试使用隔离的 OCTOP_HOME。脚本默认查找工作区 repos 下的五个仓库，其他布局传入 `--repos-root`。

QQ、Octo 的离线测试覆盖真实 Gateway 处理链、试运行、发送回执、@ 回复、配额和收件箱容量。Discord、飞书、Telegram 补齐公共元数据与设置路径；代码测试不代表各平台已经完成真实机器人联调。平台授权、发送窗口和配额仍由通道执行。

群策略要求全部消息可见范围。QQ 的权限必须在群侧开启；历史收消息故障及实测证据见[排查报告](qq-receive-diagnosis.md)。插件不能读取或代替该平台授权。

## 历史包

patches 目录和[旧验证记录](validation.md)保留 0.1.x 的接入历史，不代表当前兼容要求。host-patches-0.1.x ZIP 缺少新版接口，不能用来升级到 0.3.0；新版构建只产出插件 ZIP 和校验文件。Octop/Gateway 的配套接口尚未进入上游发行版，部署时使用通过上述接口验证的兼容构建，不能仅凭 Fork `develop` 分支名判断。

升级和迁移规则见[多通道设置](scoped-settings.md)，降级前先阅读[回滚说明](rollback.md)。
