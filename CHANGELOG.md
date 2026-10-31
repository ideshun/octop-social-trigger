# 0.3.0 — 2026-10-31

- 在放行群内 @ 前核验发送者，过滤已确认的机器人消息；未选择群、已关闭自动参与或缺少必要身份信息时，普通消息不再退回每条消息都回复的通道规则。
- 群回复支持静默标记和常见括号状态过滤，自动参与回合隐藏思考内容；需要配套 Gateway 输出保护接口，旧 Gateway 上保留试运行并暂停实际自动回复。
- 新增群消息屏蔽词，在模型调用前拦截并过滤群临时上下文；支持批量添加、搜索、删除和分页，决策模型关闭或不可用时仍生效。
- 修复关闭「被 @ 时不受回复间隔限制」后，重启后的首条 @ 可能没有检查已有冷却记录。

# 0.2.0 — 2026-10-31

- 共用多通道入站策略和可选决策模型，补齐 Octo/Discord/飞书/Telegram 规范化字段与 Octo 收件箱交接。
- 配置按全局、通道类型、实例、群和专家继承，只保存差异；支持恢复继承。
- 配置 UI 按范围和依赖重排，静默时段、模型参数与高级项按条件展示。
- v1 QQ 配置和配额状态迁移隔离命名空间，升级不自动启用其他渠道的群。
- 新包要求配套 Fork 基线，仅生成插件 ZIP，不再生成过期的宿主补丁包。

# 0.1.3 — 2026-10-30

- Added a QQ group icon and included it in the install package.
- Raised default passive reply limits to 58 per hour and 580 per day.

# 0.1.2 — 2026-10-30

- 智能模式可使用 Octop 决策模型，默认启用；服务关闭、出错、超时或达每日调用上限时回退本地规则。

# 0.1.1 — 2026-10-30

- 由插件声明 QQ 通道群聊参与开关；支持该声明的宿主仅在插件加载时显示开关。

# 0.1.0 — 2026-10-29

- Native hook entry with an explicit inbound-v1 host compatibility contract.
- QQ group selection before Agent execution, with scoped config, durable dedupe,
  quotas, cooldown, quiet hours, rule scoring, debounce, delayed dispatch and dry-run.
- Cancellation on mention/unload and conservative recovery for ambiguous sends.
- Separately packaged Gateway, Harness and Octop patches; stock hosts are refused.
- QQ platform receive-all permission verified with a real GROUP_MESSAGE_CREATE event.
  Plugin delivery in a real QQ group remains an outstanding acceptance check.
