"""Apply compatibility patches to temporary copies and run offline tests."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repos-root", type=Path, default=ROOT.parent)
    args = p.parse_args()
    repos = {
        "gateway": args.repos_root / "octop-gateway",
        "harness": args.repos_root / "octop-harness",
        "octop": args.repos_root / "Octop",
    }
    packages = {"gateway": "octop_gateway", "harness": "octop_harness", "octop": "octop"}
    baseline = json.loads((ROOT / "patches/baseline.json").read_text())
    with tempfile.TemporaryDirectory(prefix="social-trigger-verify-") as temp:
        temp = Path(temp)
        for key, repo in repos.items():
            for name, digest in baseline[key].items():
                if hashlib.sha256((repo / name).read_bytes()).hexdigest() != digest:
                    raise SystemExit(f"baseline differs: {key}/{name}; review patch compatibility before testing")
            shutil.copytree(
                repo / "src" / packages[key],
                temp / key / "src" / packages[key],
                ignore=shutil.ignore_patterns("__pycache__"),
            )
            subprocess.run(
                ["git", "apply", str(ROOT / "patches" / f"{key}-inbound-v1.patch")], cwd=temp / key, check=True
            )
        ui_baseline = json.loads((ROOT / "patches/settings-ui-baseline.json").read_text())
        for name, digest in ui_baseline.items():
            source = repos["octop"] / name
            if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise SystemExit(f"settings UI baseline differs: octop/{name}")
            dest = temp / "octop" / name
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
        subprocess.run(
            ["git", "apply", str(ROOT / "patches/octop-settings-ui-v1.patch")], cwd=temp / "octop", check=True
        )
        env = os.environ.copy()
        env["OCTOP_HOME"] = str(temp / "isolated-home")
        env.pop("OCTOP_SOCIAL_TRIGGER_CONFIG", None)
        env["PYTHONPATH"] = os.pathsep.join([str(temp / key / "src") for key in repos] + [str(ROOT)])
        # A standalone system Python intentionally cannot certify host integration.
        subprocess.run(
            [
                sys.executable,
                "-c",
                'from octop_gateway.channel import InboundReceipt; from octop_harness.plugins.context import PluginContext; from octop.infra.gateway.gateway import Gateway; assert hasattr(PluginContext,"inbound")',
            ],
            env=env,
            check=True,
            cwd=ROOT,
        )
        subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], env=env, check=True, cwd=ROOT
        )
        subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit/test_plugins.py", "-q"],
            env=env,
            check=True,
            cwd=repos["harness"],
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_channel.py",
                "tests/test_group_context.py",
                "tests/test_manager.py",
                "tests/channels/test_qq.py",
                "tests/channels/test_qq_group_commands.py",
                "-q",
                "-k",
                "not TestQQChannelIntegration",
            ],
            env=env,
            check=True,
            cwd=repos["gateway"],
        )
        subprocess.run(
            [sys.executable, "-m", "pytest", "tests/unit/test_plugin_channels.py", "-q"],
            env=env,
            check=True,
            cwd=repos["octop"],
        )
        # Actual native archive installer, isolated from ~/.octop and all live channels.
        smoke = f"""import tempfile
from pathlib import Path
from octop.infra.agents.plugins.manager import PluginManager
from octop_harness.plugins.loader import unload_plugin
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    mgr=PluginManager(plugins_dir=root/'plugins',config_path=root/'config.json')
    loaded=mgr.install_archive(Path('dist/octop-social-trigger-{VERSION}.zip'))
    assert loaded.manifest.id=='octop-social-trigger' and len(loaded.inbound)==1
    assert not loaded.inbound[0].config['enabled']
    assert unload_plugin('octop-social-trigger')
print('native_archive_install_and_unload_ok')
"""
        subprocess.run([sys.executable, "-c", smoke], env=env, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
