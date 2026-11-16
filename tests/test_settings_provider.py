"""Plugin-owned settings work without importing the Octop application."""

import pytest

from social_trigger.config import validate
from social_trigger.runtime import Runtime


@pytest.mark.asyncio
async def test_settings_provider_owns_fields_and_scopes(tmp_path):
    runtime = Runtime(validate({"schemaVersion": 2}), tmp_path / "state.db", config_path=tmp_path / "config.json")
    context = {
        "channels": [{"channelKind": "qq", "channelId": "c", "agentId": "a"}],
        "groups": [],
        "decisionModelConfigured": False,
    }
    await runtime.save_settings(context, {"scope": "defaults", "prompts": {"automaticHeader": "custom"}})
    result = await runtime.get_settings(context)
    assert result["defaults"]["policy"]["prompts"]["automaticHeader"] == "custom"
    assert result["promptDefaults"]["zh"]["automaticHeader"] == "【当前群消息｜自动参与】"
    with pytest.raises(ValueError):
        await runtime.save_settings(context, {"scope": "defaults", "prompts": {"unknown": "x"}})
    with pytest.raises(LookupError):
        await runtime.save_settings(context, {"scope": "groups", "channelId": "c", "groupId": "unobserved"})
    await runtime.wait_closed()
