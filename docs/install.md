# 安装与灰度

使用本工作区已经整合这些改动的 Octop、Gateway 和 Harness 源码时，无需重复打补丁。其他兼容源码需要 `patches/` 中三个接入补丁和 `octop-settings-ui-v1.patch` 配置界面补丁；仅安装 ZIP 不够。当前最低兼容基线与文件哈希见 `baseline.json` / [兼容性](compatibility.md)。不要直接覆盖已有未提交修改。

0.1.1 的通道开关联动还需要包含插件通道设置接口的新版 Octop 和 Gateway；本包附带的旧版宿主补丁不包含该新增接口。旧宿主仍可运行插件，但不会提供按插件加载状态显示开关的行为。

1. 先用宿主的常规方式备份配置和数据库；记录 QQ 原来的群策略。对生产实例先停止新任务。插件不读取/重写任何通道凭据。
2. 在三个源码目录分别执行对应补丁的 `git apply --check /absolute/path/to/PATCH`，核对 diff 后再 `git apply`；Octop 还需应用 `octop-settings-ui-v1.patch` 并构建 Dashboard。推荐先用源码副本运行 `make all`。补丁不更改 QQ API 域名。
3. 重新安装更新后的 Gateway/Harness/Octop 源码包到宿主虚拟环境，确保运行实例导入的是已打补丁的版本；重启测试实例。三个补丁必须一起部署。当前本机使用 editable 安装，源码包变更仍需重启进程。
4. 校验 ZIP 的 SHA-256。在管理员插件页上传 `dist/octop-social-trigger-0.1.1.zip`（宿主为 `POST /api/plugins/upload`），或者解压后执行 `octop plugin install /absolute/path/to/octop-social-trigger --force`。本机版本 CLI **不支持直接传本地 ZIP 路径**；不能照抄设计文档中的本地 ZIP 命令。
5. `octop plugin list` 核对条目。管理员插件页“重载”会更新运行实例；CLI `octop plugin reload` 仅在自己的离线进程重载，仍需服务重启或管理员重载。
6. 插件默认关闭并启用试运行。在管理后台插件详情的「群聊参与设置」中选择群、启用参与并保存；高级设置也可在 `$OCTOP_HOME/plugin-state/octop-social-trigger/config.json` 配置。插件升级不会覆盖持久配置。
7. 在 QQ 手机端确认群内全量消息授权；宿主配置 `group_context.enabled=true,visibility=all,activation=mention`，并在群聊策略开启「QQ 群聊自动参与」。该开关只允许插件接管，仍需在插件配置中启用。`activation=mention` 使插件关闭时回退到原生 @ 流程。
8. 配置只允许测试群，先 `enabled=true,dryRun=true` 并重载。普通群文本应只有决策日志，无 Agent 调用或发送；@ 回复按原路由验证。
9. 审查生效配置、去重/配额和日志后，再设置小概率及 `dryRun=false`。此操作会真实调用 Agent 并发送 QQ 回复，须由管理员明确开启。观察成功发送日志与 SQLite 计数，再扩大范围。

新增接口只负责选择/继续入站；原生命令鉴权、工具上限、Agent 安全规则、平台发送频控继续生效。插件不能取得 QQ 未授予的消息范围，不能发送平台禁止的内容或越过平台回复窗口。
