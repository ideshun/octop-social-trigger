"""Native Octop entry. Refuse hosts without the explicit inbound-v1 contract."""

import os
from pathlib import Path


def setup(ctx):
    register = getattr(ctx, "inbound", None)
    if not callable(register):
        raise RuntimeError("当前 Octop 缺少群消息接入接口，请先更新配套的 Octop Fork 基线，详见安装文档。")
    from octop_gateway.channel import InboundReceipt  # noqa: F401 — verify host contract at load time
    from octop_gateway.channel import BaseChannel

    if not callable(getattr(BaseChannel, "on_inbound_claimed", None)) or not hasattr(
        BaseChannel, "plugin_group_settings"
    ):
        raise RuntimeError("当前 Gateway 缺少多通道入站交接接口，请更新配套的 Octop Fork 基线后重载插件。")
    from .social_trigger.config import load
    from .social_trigger.runtime import Runtime

    home = Path(os.environ.get("OCTOP_HOME", str(Path.home() / ".octop")))
    persistent = home / "plugin-state" / "octop-social-trigger" / "config.json"
    default_file = persistent if persistent.is_file() else ctx.source_path / "config.json"
    config_file = Path(os.environ.get("OCTOP_SOCIAL_TRIGGER_CONFIG", default_file))
    config = load(config_file)
    register(
        Runtime(
            config,
            home / "plugin-state" / "octop-social-trigger" / "state.db",
            config_path=config_file if os.environ.get("OCTOP_SOCIAL_TRIGGER_CONFIG") else persistent,
        )
    )
