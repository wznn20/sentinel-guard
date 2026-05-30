from __future__ import annotations

import inspect
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, cwd=ROOT, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def run_embedded_tests() -> None:
    import tests.test_kx_agent as test_module

    failed: list[str] = []
    passed = 0
    for name, fn in sorted(vars(test_module).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        sig = inspect.signature(fn)
        kwargs = {}
        supported = True
        for param in sig.parameters.values():
            if param.name == "tmp_path":
                kwargs[param.name] = Path(tempfile.mkdtemp(prefix="kx-verify-"))
            else:
                supported = False
                break
        if not supported:
            continue
        try:
            fn(**kwargs)
            passed += 1
        except Exception:
            failed.append(name)
    print({"passed": passed, "failed": failed})
    if failed:
        raise SystemExit(1)


def main() -> None:
    run([sys.executable, "-m", "compileall", "kx_agent", "tests"])
    run([sys.executable, "-m", "kx_agent.cli", "self-test"])
    if importlib.util.find_spec("pytest"):
        run([sys.executable, "-m", "pytest", "-q"])
    else:
        run_embedded_tests()


if __name__ == "__main__":
    main()
