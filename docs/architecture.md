# 入站契约与时序

原始 QQ 包 → `QQChannel.parse_inbound`（保留平台 `author.bot`）→ Gateway 命令权限检查 → Octop 动态读取已启用插件的 `PluginRegistry.all_inbound()` → `Runtime.handle()`。

普通输入被接管后，运行时在每个租户/实例/群/Agent 的短锁内去重并更新内存窗口，随后返回 worker。异步任务在锁外防抖、规则判定、原子预占、随机等待，再调用 Gateway 提供的 `dispatch()`。此续处理回调重新核验通道仍注册，在原生会话锁内执行 `handle_inbound(force_activation=True)`；Gateway 仅在启用群策略且显式 `visibility=all` 时允许覆盖 activation。命令和 @ 不被伪造为普通消息，未获授权的处理不会被恢复。

强制激活只附带插件审查过且仍在 TTL 内的上下文，不混入宿主更长 TTL 的被动缓存；宿主的命令/工具权限过滤继续执行。普通新消息会取消同作用域尚未完成的被动任务并重新合并；@ 会清空窗口并取消被动任务，再走原生 @ 路由。

`InboundReceipt` 通过 ContextVar 关联本轮的 `reply_text/content/media`，记录发送是否尝试、是否至少成功一次。它独立于原有 `processing_succeeded`：空的 COMPLETED 不算发送。成功提交计数；未尝试的取消释放预占；尝试后无明确成功视为未知，保留 pending。QQ 群的标准 buffered 输出是 v1 验证范围，其他自定义流式通道未声明兼容。

Harness 的 `ctx.inbound(handler)` 是本仓库补丁引入的新接口，要求 `kind=hook` 和 `handle/close`。清空、替换、卸载注册时调用 close；Octop 关闭 Gateway 时等待可选的 `wait_closed()`，取消窗口和延迟任务。尚未打补丁的宿主没有此接口，插件入口会报明确不兼容错误。未注册入站策略时 Gateway 保持原处理流程。
