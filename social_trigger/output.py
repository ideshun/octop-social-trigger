"""Suppress explicit no-reply output in group responses."""

import re


_STATUS = re.compile(
    r"(?:(?:先|暂时|暂且|目前|现在)?不(?:再|用|要|必)?"
    r"(?:回(?:复|应|答|话)?|插话|介入|参与|发言|说话|作答|出声)(?:[，,、\s].*)?"
    r"|(?:先)?(?:等|等待)[^。！？\n]{0,20}(?:消息|打字|发言|回复|开口|回应)"
    r"|(?:无|没有|暂无)(?:新)?(?:消息|信息|内容)"
    r"|(?:略|跳过|沉默)"
    r"|叫\s*[\w·-]{1,16})[。.!！…\s]*"
)


def _classification_text(text: str) -> str:
    value = text.strip().strip("`*_").strip()
    return re.sub(r"^@[^\n()（）\[\]<>]{1,40}\s*(?=[（(\[<])", "", value).strip()


def filter_group_reply(text: str) -> str:
    """Drop a no-reply marker or a standalone parenthesized status/action."""
    value = _classification_text(text)
    if value.rstrip("。.!！… ").upper() in {"NO_REPLY", "[NO_REPLY]", "<NO_REPLY>"}:
        return ""
    if len(value) >= 2 and (value[0], value[-1]) in {("（", "）"), ("(", ")")}:
        if _STATUS.fullmatch(value[1:-1].strip()):
            return ""
    return text


class GroupReplyFilter:
    """Hold an unfinished marker across stream flushes within one reply."""

    def __init__(self, on_suppressed):
        self._pending = ""
        self._on_suppressed = on_suppressed

    def __call__(self, text: str) -> str:
        candidate = self._pending + text
        value = _classification_text(candidate)
        upper = value.upper()
        unfinished_bracket = (value.startswith("（") and "）" not in value) or (
            value.startswith("(") and ")" not in value
        )
        unfinished_marker = bool(value) and any(
            marker.startswith(upper) and marker != upper for marker in ("[NO_REPLY]", "<NO_REPLY>")
        )
        if len(value) <= 512 and (unfinished_bracket or unfinished_marker):
            self._pending = candidate
            return ""
        self._pending = ""
        filtered = filter_group_reply(candidate)
        if candidate and not filtered:
            self._on_suppressed()
        return filtered
