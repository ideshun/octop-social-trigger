import pytest

from social_trigger.output import GroupReplyFilter, filter_group_reply, sanitize_group_reply


@pytest.mark.parametrize(
    "text",
    [
        "[NO_REPLY]",
        "[NO_REPLY]。",
        "`[NO_REPLY]`",
        "@成员甲 [NO_REPLY]",
        "（不回复）",
        "（不介入。）",
        "（等文字消息。）",
        "（略。）",
        "（叫机器人甲。）",
        "（不插话，等成员甲。）",
        "@成员甲 （等文字消息。）",
    ],
)
def test_group_reply_suppresses_no_reply_markers_and_statuses(text):
    assert filter_group_reply(text) == ""


@pytest.mark.parametrize(
    "text",
    [
        "（推荐方案 A。）",
        "@成员甲 （推荐方案 A。）",
        "（让服务重启。）",
        "可以这样做（先备份）。",
        "等构建完成后再部署。",
        "哈哈这图我也看到过",
        "真的假的",
    ],
)
def test_group_reply_preserves_substantive_text(text):
    assert filter_group_reply(text) == text


def test_group_reply_filter_holds_split_status_and_preserves_split_normal_reply():
    suppressed = []
    guard = GroupReplyFilter(lambda: suppressed.append(True))
    assert guard("（不") == ""
    assert suppressed == []
    assert guard("介入。）") == ""
    assert suppressed == [True]

    assert guard("（推荐") == ""
    assert guard("方案 A。）") == "（推荐方案 A。）"
    assert suppressed == [True]

    assert guard("[NO_") == ""
    assert guard("REPLY]") == ""
    assert suppressed == [True, True]


def test_group_reply_filter_handles_bare_marker_and_trailing_punctuation():
    guard = GroupReplyFilter(lambda: None)
    assert guard("NO_") == ""
    assert guard("REPLY") == ""
    assert guard("。") == ""
    assert guard("actual answer") == "actual answer"
    assert guard.finish() == ""


def test_group_reply_filter_releases_unclosed_normal_text_at_end():
    guard = GroupReplyFilter(lambda: None)
    assert guard("（推荐方案") == ""
    assert guard.finish() == "（推荐方案"
    assert guard.finish() == ""


def test_group_reply_strips_fabricated_tool_trace_and_html_dump():
    dirty_sample = (
        '**Tool call**: web_fetch　`{"url": "https://www.bing.com/search?q=Riemann+hypothesis+Claude+proof+news"}`'
        '　`{"url": "..."}`\n\n'
        "**Tool result**:\n"
        "```\n"
        '[status: ok] <html lang="en-US"><head><title>Riemann hypothesis Claude proof news - Bing</title>\n'
        '<meta name="description" content="Smart search: No good results found for your search term.">\n'
        "```\n\n"
        "我又查了一遍，还是没搜到任何可信报道。等数学机构确认再说。"
    )
    assert sanitize_group_reply(dirty_sample) == "我又查了一遍，还是没搜到任何可信报道。等数学机构确认再说。"
    assert filter_group_reply(dirty_sample) == "我又查了一遍，还是没搜到任何可信报道。等数学机构确认再说。"


def test_group_reply_suppresses_pure_tool_trace_and_triggers_on_suppressed():
    pure_trace = (
        '**Tool call**: web_fetch `{"url": "https://example.com"}`\n\n'
        "**Tool result**:\n"
        "```html\n"
        "[status: ok] <html><body>Error</body></html>\n"
        "```\n"
    )
    assert filter_group_reply(pure_trace) == ""
    suppressed = []
    guard = GroupReplyFilter(lambda: suppressed.append(True))
    assert guard(pure_trace) == ""
    assert suppressed == [True]


def test_group_reply_preserves_normal_code_fence_and_strips_traceback_and_diagnostic_fence():
    normal_code = "你可以用下面这段代码：\n\n```python\ndef add(a, b):\n    return a + b\n```\n\n这样就能正常跑通了。"
    assert filter_group_reply(normal_code) == normal_code

    with_traceback = (
        "刚才请求接口失败了：\n\n"
        "Traceback (most recent call last):\n"
        '  File "/app/main.py", line 10, in run\n'
        "    resp = fetch()\n"
        "RuntimeError: connection timeout\n\n"
        "稍后再试一次吧。"
    )
    assert filter_group_reply(with_traceback) == "刚才请求接口失败了：\n\n稍后再试一次吧。"


def test_group_reply_filter_holds_unfinished_tool_fence_across_chunks():
    suppressed = []
    guard = GroupReplyFilter(lambda: suppressed.append(True))
    assert guard('**Tool call**: web_fetch `{"url": "https://example.com"}`\n\n**Tool result**:\n```') == ""
    assert guard("\n[status: ok] <html><head></head></html>") == ""
    assert guard("\n```\n\n查完了，没有新消息。") == "查完了，没有新消息。"
    assert guard.finish() == ""
    assert suppressed == []

    # Pure unfinished trace held until finish() should record silent_output.
    assert guard('**Tool call**: web_fetch `{"url": "https://example.com"}`') == ""
    assert guard.finish() == ""
    assert suppressed == [True]
