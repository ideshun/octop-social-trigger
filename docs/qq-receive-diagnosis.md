# QQ 全量群消息接收排查（2026-10-29）

## 已确认的本次根因

用户找到并启用 QQ 群内机器人消息接收范围设置后，2026-10-29 15:20:58 首次观察到 `GROUP_MESSAGE_CREATE`；本机 QQ 群会话的持久路由 metadata 同时更新为该事件。期间没有修改运行实例的 Gateway 接收代码或切换 API 域名。因此，本次未收到普通群消息的原因是 QQ 群侧接收范围授权尚未开启，不是本机 Gateway 缺少该事件处理。下面的域名兼容性差异独立存在，但没有证据证明它造成了本次故障。

## 排查过程与证据边界

QQ 官方明确支持全量群消息。当前本机 octop-gateway 源码也已识别该事件，不能以“QQ 不支持”解释此次现象。已确认本机接入域名落后于官方变更要求；但旧域名是否导致本次普通群消息缺失尚未实测确认，不能将兼容性差异等同于已查明的收信根因。

官方原文已通过不带认证信息的 HTTPS 请求直接读取；网页搜索工具对其中部分页面返回不可访问，不影响这次直接读取的结果。

## 官方文档核对

- [群消息（全量模式）](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html)：开启接收所有消息后，下发 `GROUP_MESSAGE_CREATE`；Intent 为 `GROUP_AND_C2C_EVENT (1<<25)`。`author` 的类型包含 `bot` 字段。此前“没有可用机器人标记”的判断只适用于 Gateway 当前未保留的规范化 metadata，并不是官方事件没有这个字段。
- [变更记录](https://bot.q.qq.com/wiki/develop/api-v2/changelog.html)：2026-08-10 起所有接口调用域名统一为 `api.bot.qq.com`。
- [WebSocket 方式](https://bot.q.qq.com/wiki/develop/api-v2/dev-prepare/event-emit/websocket.html)：当前文档示例接入地址为 `wss://api.bot.qq.com/websocket/`，无分片时使用 `[0,1]`。
- [官方 FAQ](https://bot.q.qq.com/wiki/bot_FAQ/)：要求最新版 iOS/Android QQ，以群主身份添加 QQBot 入群时点击“设置权限”，并允许机器人接收群内全部消息。此前只要求在群设置中寻找开关的指引不完整。该说明不意味着应未经确认删除现有机器人。
- [群机器人状态](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_bot_state.get.html)：`recv_msg_setting` 文档值为 `all`、`only_mention`、`mention_and_context`，空字符串的语义没有说明。

## 本机源码与实验

- Gateway commit：`ffbd34b4cd7dd3833054c88912123281adcfb377`，工作树有用户既有修改。
- `channels/qq/channel.py` 默认 intents 包含 `1<<25`；`_handle_dispatch` 包含 `GROUP_MESSAGE_CREATE`，并在去重/入队之前记录收到的事件。
- API base 仍为 `https://api.sgroup.qq.com`，取 token 使用 `https://bots.qq.com/app/getAppAccessToken`。这与当前官方要求存在兼容性差异。
- 按照 `visibility=all`、`activation=always`、仅所有者调用工具的配置，模拟普通群事件可经过事件分发、入队、群策略进入 processor，工具权限被正确限制；测试没有连接 QQ 网络，也不能证明运行实例与平台交互正常。
- 实际日志已观察到 @ 事件，未观察到 `GROUP_MESSAGE_CREATE`。日志缺失只是边界证据，不能排除实际进程、日志配置或 QQ 下发范围的差异。
- 使用当前实例身份，通过既有 `api.sgroup.qq.com` 查询最近活跃的群，HTTP 200，`member_role=member`，`recv_msg_setting=""`。查询的是机器人角色，不是操作者是否为群主；空值不能解释成已经开通或已关闭全量权限。
- 对 `api.bot.qq.com` 携带 token 的只读复核被自动审批拒绝，未执行。因而没有新旧接口对比结论。

## 后续如何确认根因

1. 用最新版手机 QQ 核实目标机器人在目标群的全量消息授权，按官方 FAQ 的“添加到群 → 设置权限”入口确认；不要把 Octop 界面的 visibility 当作 QQ 授权。
2. 在明确授权且自动审批允许后，通过文档统一域名查询同一群状态并比较接入地址；未知/空状态必须保留为未知。
3. 在实际运行进程记录不含内容的 WebSocket 事件类型/序列与入队结果，做普通消息与 @ 消息的同时间对照。若入站有事件但未入队，修 Gateway；若未入站，继续核对 QQ 授权/推送链路。
4. API 域名迁移需单独测试并验证运行实例；迁移前后有可对照的实际事件，才能证明是否修复这次故障。
