from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = "wznn20/sentinel-guard"
LATEST_WHEEL = f"https://github.com/{REPO}/releases/latest/download/kx_agent-latest-py3-none-any.whl"


def main() -> None:
    tag = sys.argv[1] if len(sys.argv) > 1 else "dev"
    version = tag[1:] if tag.startswith("v") else tag
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    payload = {
        "tag": tag,
        "version": version,
        "repo": REPO,
        "assets": {
            "latest_wheel": LATEST_WHEEL,
            "versioned_wheel_glob": f"{base}/kx_agent-{version}-*.whl",
            "versioned_sdist": f"{base}/kx_agent-{version}.tar.gz",
        },
        "install": {
            "pip_latest": f"pip install --upgrade {LATEST_WHEEL}",
            "pip_versioned": f"pip install --upgrade {base}/kx_agent-{version}-py3-none-any.whl",
        },
    }
    Path("release-manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
