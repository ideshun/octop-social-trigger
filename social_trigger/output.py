"""Suppress explicit no-reply output and leaked tool/diagnostic traces in group responses."""

import re


_STATUS = re.compile(
    r"(?:(?:先|暂时|暂且|目前|现在)?不(?:再|用|要|必)?"
    r"(?:回(?:复|应|答|话)?|插话|介入|参与|发言|说话|作答|出声)(?:[，,、\s].*)?"
    r"|(?:先)?(?:等|等待)[^。！？\n]{0,20}(?:消息|打字|发言|回复|开口|回应)"
    r"|(?:无|没有|暂无)(?:新)?(?:消息|信息|内容)"
    r"|(?:略|跳过|沉默)"
    r"|叫\s*[\w·-]{1,16})[。.!！…\s]*"
)

_TOOL_HEADER_RE = re.compile(
    r"^[ \t\u3000]*(?:[-*>][ \t\u3000]+)?(?:\*\*|__|`)*"
    r"(?:Tool[ \t\u3000]+(?:call|result|output)s?|Function[ \t\u3000]+(?:call|result|output)s?|工具(?:调用|结果|返回|输出))"
    r"(?:\*\*|__|`)*[ \t\u3000]*[:：](?:\*\*|__|`)*",
    re.IGNORECASE,
)

_TRACEBACK_HEADER_RE = re.compile(
    r"^[ \t\u3000]*(?:\*\*|__|`)*Traceback[ \t\u3000]+\(most[ \t\u3000]+recent[ \t\u3000]+call[ \t\u3000]+last\)[ \t\u3000]*[:：]?(?:\*\*|__|`)*[ \t\u3000]*$",
    re.IGNORECASE,
)

_STATUS_LINE_RE = re.compile(
    r"^[ \t\u3000]*\[status:[ \t\u3000]*(?:ok|error|failed|success|[0-9]{3})\](?:[ \t\u3000]+.*)?$",
    re.IGNORECASE,
)

_RAW_HTML_LINE_RE = re.compile(
    r"^[ \t]*<(?:!doctype\b|/?(?:html|head|meta|body)\b)[^>]*>.*$",
    re.IGNORECASE,
)

_DIAG_FENCE_LANG_RE = re.compile(
    r"^(?:html|xml|traceback|tool|tool_call|tool_result|console)\b",
    re.IGNORECASE,
)

_EXCEPTION_TAIL_RE = re.compile(
    r"^[ \t]*[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt|Exit)(?:[ \t]*:.*)?$"
)


def _is_diagnostic_fence(lang: str, body: str, *, after_tool_header: bool) -> bool:
    if after_tool_header:
        return True
    if _DIAG_FENCE_LANG_RE.match(lang.strip()):
        return True
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if (
            _STATUS_LINE_RE.match(line)
            or _RAW_HTML_LINE_RE.match(line)
            or _TRACEBACK_HEADER_RE.match(line)
            or _TOOL_HEADER_RE.match(line)
        ):
            return True
    return False


def _is_raw_trace_line(line: str) -> bool:
    return bool(_STATUS_LINE_RE.match(line) or _RAW_HTML_LINE_RE.match(line))


def sanitize_group_reply(text: str) -> str:
    """Strip fabricated tool traces, raw HTML/status dumps, and tracebacks while keeping prose and normal code blocks."""
    if not text:
        return ""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    after_tool_header = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            out.append("")
            i += 1
            continue

        # 1. Fenced code block: drop only when tied to a tool trace or containing raw HTML/status/traceback diagnostics.
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            j = i + 1
            body_lines: list[str] = []
            while j < n and not lines[j].strip().startswith("```"):
                body_lines.append(lines[j])
                j += 1
            body = "\n".join(body_lines)
            if _is_diagnostic_fence(lang, body, after_tool_header=after_tool_header):
                after_tool_header = False
            else:
                out.extend(lines[i : min(j + 1, n)])
                after_tool_header = False
            i = j + 1 if j < n else n
            continue

        # 2. Tool call / Tool result header paragraph.
        if _TOOL_HEADER_RE.match(line):
            after_tool_header = True
            i += 1
            while i < n:
                cur = lines[i]
                cur_stripped = cur.strip()
                if not cur_stripped:
                    i += 1
                    break
                if cur_stripped.startswith("```") or _TOOL_HEADER_RE.match(cur):
                    break
                if _is_raw_trace_line(cur) or cur[:1] in (" ", "\t") or cur_stripped.startswith(("{", "[", "`")):
                    i += 1
                    continue
                break
            continue

        # 3. Python traceback block.
        if _TRACEBACK_HEADER_RE.match(line):
            after_tool_header = False
            i += 1
            while i < n:
                cur = lines[i]
                cur_stripped = cur.strip()
                if not cur_stripped:
                    i += 1
                    break
                if (
                    cur[:1] in (" ", "\t")
                    or cur_stripped.startswith(('File "', "During handling of", "The above exception"))
                    or _EXCEPTION_TAIL_RE.match(cur)
                ):
                    i += 1
                    continue
                break
            continue

        # 4. Standalone raw status or HTML dump line.
        if _is_raw_trace_line(line):
            after_tool_header = False
            i += 1
            continue

        after_tool_header = False
        out.append(line)
        i += 1

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return cleaned


def _has_unfinished_trace(text: str) -> bool:
    """True when streaming text is mid-fence or mid-tool/traceback block."""
    lines = text.splitlines()
    fence_count = sum(1 for line in lines if line.strip().startswith("```"))
    if fence_count % 2 == 1:
        return True
    non_empty = [line for line in lines if line.strip()]
    if non_empty:
        last_line = non_empty[-1]
        if (
            _TOOL_HEADER_RE.match(last_line) and not _TOOL_HEADER_RE.sub("", last_line).strip()
        ) or _TRACEBACK_HEADER_RE.match(last_line):
            return True
    tail = text.rsplit("\n\n", 1)[-1]
    if not tail.strip():
        return False
    tail_lines = tail.splitlines()
    if any(line.strip().startswith("```") for line in tail_lines):
        return False
    return any(_TOOL_HEADER_RE.match(line) or _TRACEBACK_HEADER_RE.match(line) for line in tail_lines)


def _classification_text(text: str) -> str:
    value = text.strip().strip("`*_").strip()
    return re.sub(r"^@[^\n()（）\[\]<>]{1,40}\s*(?=[（(\[<])", "", value).strip()


def filter_group_reply(text: str) -> str:
    """Sanitize diagnostic leaks and drop a no-reply marker or standalone parenthesized status/action."""
    if not text:
        return ""
    sanitized = sanitize_group_reply(text)
    if not sanitized:
        return ""
    value = _classification_text(sanitized)
    if value.rstrip("。.!！… ").upper() in {"NO_REPLY", "[NO_REPLY]", "<NO_REPLY>"}:
        return ""
    if len(value) >= 2 and (value[0], value[-1]) in {("（", "）"), ("(", ")")}:
        if _STATUS.fullmatch(value[1:-1].strip()):
            return ""
    return sanitized if sanitized != text.strip() else text


class GroupReplyFilter:
    """Hold an unfinished marker or diagnostic block across stream flushes within one reply."""

    def __init__(self, on_suppressed, on_sanitized=None):
        self._pending = ""
        self._on_suppressed = on_suppressed
        self._on_sanitized = on_sanitized
        self._silent_tail = False

    def _note_if_sanitized(self, raw: str, filtered: str) -> None:
        if not filtered or self._on_sanitized is None:
            return
        normalized_raw = re.sub(r"\n{3,}", "\n\n", "\n".join(raw.splitlines())).strip()
        if filtered.strip() != normalized_raw:
            self._on_sanitized()

    def __call__(self, text: str) -> str:
        if self._silent_tail and not text.strip("。.!！… \t\r\n"):
            return ""
        self._silent_tail = False
        candidate = self._pending + text
        value = _classification_text(candidate)
        upper = value.upper()
        unfinished_bracket = (value.startswith("（") and "）" not in value) or (
            value.startswith("(") and ")" not in value
        )
        unfinished_marker = bool(value) and any(
            marker.startswith(upper) and marker != upper for marker in ("NO_REPLY", "[NO_REPLY]", "<NO_REPLY>")
        )
        if (len(value) <= 512 and (unfinished_bracket or unfinished_marker)) or (
            len(candidate) <= 16384 and _has_unfinished_trace(candidate)
        ):
            self._pending = candidate
            return ""
        self._pending = ""
        filtered = filter_group_reply(candidate)
        if candidate and not filtered:
            self._silent_tail = True
            self._on_suppressed()
        else:
            self._note_if_sanitized(candidate, filtered)
        return filtered

    def finish(self) -> str:
        """Release non-marker text held until the end of a completed stream."""
        pending, self._pending = self._pending, ""
        self._silent_tail = False
        if not pending:
            return ""
        filtered = filter_group_reply(pending)
        if not filtered:
            self._on_suppressed()
        else:
            self._note_if_sanitized(pending, filtered)
        return filtered
