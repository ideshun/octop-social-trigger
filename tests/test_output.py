import pytest

from social_trigger.output import GroupReplyFilter, filter_group_reply


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
