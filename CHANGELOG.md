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
