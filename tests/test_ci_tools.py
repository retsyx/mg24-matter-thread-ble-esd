"""Exercise CI setup when SLC replaces ZAP in its shared install directory."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build-firmware.yml"
PINNED_ZAP = "2026.09.18"
DEPENDENCY_ZAP = "2027.01.01"  # Hypothetical future SLC dependency beyond our pin.


def install_script():
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index("      - name: Install pinned SDK and build tools")
    start = lines.index("        run: |", start) + 1
    end = next((i for i in range(start, len(lines))
                if lines[i] and not lines[i].startswith("          ")), len(lines))
    return textwrap.dedent("\n".join(lines[start:end]))


MOCK_SLT = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import sys

root = Path(os.environ["MOCK_SLT_STATE"])
pinned_zap = os.environ["MOCK_ZAP_PIN"]
dependency_zap = os.environ["MOCK_ZAP_DEPENDENCY"]
state_file = root / "state.json"
state = json.loads(state_file.read_text())
args = [arg for arg in sys.argv[1:] if arg != "--non-interactive"]

def install(reference, force=False):
    if reference in state["installed"] and not force:
        return
    name, version = reference.split("/", 1)
    path = root / ("zap" if name == "zap" else name + "-" + version)
    if name == "slc-cli":
        install("zap/" + dependency_zap, force=True)
        state["slc_overwrites"] += 1
    if name == "zap" and version == pinned_zap and os.environ["MOCK_ZAP_RESULT"] == "wrong-version":
        return  # Model a nominally successful install that leaves the newer binary.
    path.mkdir(exist_ok=True)
    if name == "zap":
        state["zap_version"] = version
        (path / "version").write_text(version)
        if version == pinned_zap and os.environ["MOCK_ZAP_RESULT"] == "missing-directory":
            shutil.rmtree(path)
    state["installed"][reference] = str(path)

if args[0] == "install":
    for reference in args[1:]:
        if not reference.startswith("-"):
            install(reference, force="--force" in args)
    state_file.write_text(json.dumps(state))
elif args[0] == "where":
    reference = args[1]
    if (reference not in state["installed"] or
            reference.startswith("zap/") and reference.split("/", 1)[1] != state["zap_version"]):
        sys.exit("no results found")
    print(state["installed"][reference])
else:
    sys.exit("unexpected SLT command")
'''


class WorkflowToolsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mg24-ci-tools-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.zap = self.root / "zap"
        self.zap.mkdir()
        (self.zap / "version").write_text(PINNED_ZAP)
        # A cache can retain the pinned registration even after SLC overwrites its files.
        (self.root / "state.json").write_text(json.dumps({
            "installed": {"zap/" + PINNED_ZAP: str(self.zap)},
            "zap_version": PINNED_ZAP,
            "slc_overwrites": 0,
        }))
        mock = self.root / "slt"
        mock.write_text(MOCK_SLT)
        mock.chmod(0o755)

    def run_setup(self, result="success"):
        env = dict(os.environ, MOCK_SLT_STATE=str(self.root), MOCK_ZAP_RESULT=result,
                   MOCK_ZAP_PIN=PINNED_ZAP, MOCK_ZAP_DEPENDENCY=DEPENDENCY_ZAP)
        env["PATH"] = str(self.root) + os.pathsep + env.get("PATH", "")
        return subprocess.run(["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c",
                               install_script()], cwd=self.root, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_pinned_zap_is_restored_after_slc_overwrites_it(self):
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = json.loads((self.root / "state.json").read_text())
        self.assertEqual(state["slc_overwrites"], 1)
        self.assertEqual((self.zap / "version").read_text(), PINNED_ZAP)

    def test_successful_install_leaving_wrong_version_is_rejected(self):
        result = self.run_setup("wrong-version")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.zap / "version").read_text(), DEPENDENCY_ZAP)
        self.assertIn("no results found", result.stderr)

    def test_successful_install_returning_missing_directory_is_rejected(self):
        result = self.run_setup("missing-directory")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.zap.exists())
        self.assertIn("invalid package directory", result.stdout)


if __name__ == "__main__":
    unittest.main()
