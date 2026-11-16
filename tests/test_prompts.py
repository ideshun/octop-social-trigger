"""Prompt defaults and scene rendering belong to this plugin."""

import pytest
from octop_gateway.models import GroupContext, InboundMessage, TextContent

from social_trigger.prompts import render_inbound_text


@pytest.mark.parametrize("automatic", [True, False])
def test_custom_prefixes_preserve_reply_scene(automatic):
    message = InboundMessage(
        channel_id="test",
        channel_type="qq",
        content=[TextContent(text="current")],
        metadata={
            "social_trigger_render": True,
            "social_trigger_auto": automatic,
            "social_trigger_output_guard": True,
            "sender_id": "same",
            "sender_name": "Alice",
            "reply_quote_text": "quoted",
            "social_trigger_prompts": {
                "automaticHeader": "[auto]",
                "directHeader": "[direct]",
                "quoteHeader": "[quote]",
            },
        },
        group_context=GroupContext(conversation_id="g", visibility="all", activation="mention"),
    )
    text = render_inbound_text(
        message,
        message.text,
        background=[{"sender_id": "same", "sender_name": "", "segments": ["previous"]}],
        locale="zh",
    )
    assert "[Alice] previous" in text
    assert ("[auto]" if automatic else "[direct]") in text
    assert "[quote]\n  quoted" in text
    assert "[NO_REPLY]" in text
    assert message.text == "current"


def test_renderer_declines_messages_outside_plugin():
    message = InboundMessage(channel_id="test", content=[TextContent(text="hello")])
    assert render_inbound_text(message, message.text, background=[], locale="zh") is None
