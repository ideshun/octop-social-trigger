"""Verify the configured source baseline and native archive in an isolated home."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repos-root", type=Path, default=ROOT.parents[1] / "repos")
    args = parser.parse_args()
    sources = [
        args.repos_root / name / "src"
        for name in ("Octop", "octop-gateway", "octop-harness", "octop-memory", "octop-browser")
    ]
    if not all(path.is_dir() for path in sources):
        raise SystemExit("Pass --repos-root pointing to the five compatible source repositories")
    with tempfile.TemporaryDirectory(prefix="social-trigger-verify-") as temp:
        env = os.environ.copy()
        env["OCTOP_HOME"] = str(Path(temp) / "home")
        env.pop("OCTOP_SOCIAL_TRIGGER_CONFIG", None)
        env["PYTHONPATH"] = os.pathsep.join(str(path) for path in [*sources, ROOT, ROOT.parent / "octop-channel-octo"])
        contract = """
from octop_gateway.channel import BaseChannel, InboundReceipt
from octop_harness.plugins.context import PluginContext
assert callable(getattr(BaseChannel, "on_inbound_claimed", None))
assert hasattr(BaseChannel, "plugin_group_settings")
assert hasattr(PluginContext, "inbound")
"""
        subprocess.run([sys.executable, "-c", contract], env=env, cwd=ROOT, check=True)
        subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "--basetemp", str(Path(temp) / "pytest")],
            env=env,
            cwd=ROOT,
            check=True,
        )
        smoke = f"""
from pathlib import Path
from octop.infra.agents.plugins.manager import PluginManager
from octop_harness.plugins.loader import unload_plugin
mgr = PluginManager(plugins_dir=Path({temp!r}) / "plugins", config_path=Path({temp!r}) / "config.json")
loaded = mgr.install_archive(Path("dist/octop-social-trigger-{VERSION}.zip"))
assert loaded.inbound[0].settings_version == 2
assert not loaded.inbound[0].config["enabled"]
assert loaded.inbound[0].config["dryRun"]
assert loaded.inbound[0].config["allowGroups"] == []
assert unload_plugin("octop-social-trigger")
print("native_archive_install_and_unload_ok")
"""
        subprocess.run([sys.executable, "-c", smoke], env=env, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
