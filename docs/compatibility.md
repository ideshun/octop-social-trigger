# 兼容性与验证范围

补丁以本地合入待评审 PR 后的三个仓库提交为基线。精确文件 SHA-256 在 `patches/baseline.json` 和 `settings-ui-baseline.json`；校验脚本要求输入未打补丁的基线源码。

| 项目 | 补丁基线提交 |
| --- | --- |
| Octop | `ad9802a5426db53d4dad203cdccdc02e5be61258` |
| octop-gateway | `5eb32f44b48fad8721eea9dabbe4d52a0d081b96` |
| octop-harness | `8988186dc68b7df900e92ab08aaadd16174276d7` |

标准宿主没有本插件需要的 pre-agent 注册接口。本版提供 `gateway-inbound-v1.patch`、`harness-inbound-v1.patch`、`octop-inbound-v1.patch`，分别实现前置续处理/发送回执、注册与卸载、运行实例桥接。它们是单独的源码补丁，不是既有 `ctx.middleware()` 的行为，也没有 monkey-patch 私有方法。当前未创建或发布上游 PR。

自动化测试先在隔离副本应用补丁，并用真实 `PluginManager.install_archive` 在临时目录验证安装。0.1.2 的 Octop 通道设置和决策模型接入已在当前 Fork 自动化验证，并部署到本机 Octop 检查服务健康及管理界面。此次没有对该版本发送新的 QQ 群测试消息；此前的真实回复验收针对旧版插件。通过本机测试不代表兼容其他版本或其他部署。

## 已验证的边界

- QQ 平台真实入口：2026-10-29 15:20:58 观察到 `GROUP_MESSAGE_CREATE`，对应群会话的持久 metadata 同时记录该事件。用户启用 QQ 群侧接收范围后恢复，期间没有修改 Gateway 或 API 域名；本次故障根因是群侧授权尚未开启。见 [排查报告](qq-receive-diagnosis.md)。
- 插件策略/状态、四 worker Gateway 队列、原生 processor/模拟发送、Native loader 与卸载：离线自动化测试。
- 宿主原有 Gateway 群上下文、QQ 普通/命令处理与 Harness/Octop 插件注册：隔离副本回归测试。具体数量及限制见 `validation.md`。
- SQLite 多进程配额竞争、状态重建、失败释放：自动化测试。跨主机部署与分布式合并不在范围内。

## 当前客观限制

QQ 全量消息依赖群主使用最新版移动 QQ 设置接收范围；Octop 的 visibility 不会授予 QQ 权限。旧 API 域名与当前官方域名存在独立的兼容性差异，本补丁没有切换域名，不能把这项差异当成本次故障的已证实原因。

v1 的输入/发送链资格限定 QQ 群普通文本，要求可靠的 `author.bot`。未知机器人身份、群可见性或稳定 Agent ID 时跳过非 @。QQ 回复窗口、App 权限、频率和平台审核仍由官方通道执行，不能保证平台允许所有已接收事件的回复。

常用设置由 Octop Dashboard 兼容改动提供；在未包含该界面的源码基线上还需应用 `octop-settings-ui-v1.patch` 并构建前端。旧 `classifier` 字段不控制 0.1.2 决策模型；其他通道自动参与和冷场主动发言未交付，高级规则仍可使用 JSON 配置。
