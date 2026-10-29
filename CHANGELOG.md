# 0.1.0 — 2026-10-29

- Native hook entry with an explicit inbound-v1 host compatibility contract.
- QQ group selection before Agent execution, with scoped config, durable dedupe,
  quotas, cooldown, quiet hours, rule scoring, debounce, delayed dispatch and dry-run.
- Cancellation on mention/unload and conservative recovery for ambiguous sends.
- Separately packaged Gateway, Harness and Octop patches; stock hosts are refused.
- QQ platform receive-all permission verified with a real GROUP_MESSAGE_CREATE event.
  Plugin delivery in a real QQ group remains an outstanding acceptance check.
