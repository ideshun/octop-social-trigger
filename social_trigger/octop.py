"""Normalize an Octop Gateway InboundMessage; no registration is performed."""

from .core import Message


def normalize(inbound, *, agent_id, visibility_granted, sender_is_bot):
    """Return None for non-groups. Capability and bot identity must be verified by host."""
    meta = inbound.metadata
    subject = inbound.channel_subject
    if meta.get("chat_type") != "group" and not (subject and subject.chat_type == "group"):
        return None
    if type(sender_is_bot) is not bool:
        raise ValueError("sender_is_bot must be verified by the host")
    group_id = meta.get("conversation_id") or (subject.subject_id if subject else "")
    sender_id = meta.get("sender_id")
    if not isinstance(sender_id, str) or sender_id in ("", "unknown"):
        raise ValueError("stable sender ID is unavailable")
    if type(meta.get("bot_mentioned")) is not bool:
        raise ValueError("bot mention status is unavailable")
    return Message(
        platform=inbound.channel_type,
        channelInstanceId=inbound.channel_id,
        tenantId=inbound.tenant_id or "",
        groupId=group_id,
        agentId=agent_id,
        messageId=str(meta.get("msg_id") or meta.get("message_id") or ""),
        senderId=sender_id,
        text=inbound.text,
        receivedAt=inbound.timestamp,
        isMentioned=meta["bot_mentioned"],
        isReplyToBot=meta.get("reply_to_bot") is True,
        isBotMessage=sender_is_bot,
        isCommand=inbound.text.lstrip().startswith("/"),
        visibilityGranted=visibility_granted,
    )
