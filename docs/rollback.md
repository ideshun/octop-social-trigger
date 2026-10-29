# 停用、卸载、回滚

1. 在插件详情的「群聊参与设置」中关闭参与并保存。旧实例的待发任务会被取消，内存上下文清空。禁用会恢复宿主原路由；若原生 `activation=always`，它仍会逐条回复。推荐保留 `activation=mention` 回退配置。
2. 暂不需要时，在管理员插件页禁用；卸载可使用 `octop plugin uninstall octop-social-trigger` 后管理员重载或服务重启。CLI 自身操作不能直接取消另一运行进程的任务。
3. 确认没有待发任务后，停止宿主实例，分别用 `git apply -R --check PATCH` 核对，再 `git apply -R PATCH` 撤回设置界面补丁和三个接入兼容补丁。只撤回本补丁，不使用 `git reset --hard` 或覆盖用户既有改动。重新安装源码包、构建 Dashboard 并重启。
4. 如曾调整 QQ 通道群策略，仅恢复相应 `group_context` 字段。不得整体覆盖通道配置或凭据。
5. 保留私有状态数据库用于审计/恢复；确定不再需要后由管理员删除 `$OCTOP_HOME/plugin-state/octop-social-trigger/`。pending 不会自动过期，发送结果不明时不得假定未发送。用 `status/resolve` 核实处理。

已完成的平台发送无法通过取消本地任务撤回。跨进程/传输超时的结果不确定时，插件保守停止该作用域的后续被动触发；重载不会重发原输入。
