#!/usr/bin/env python3
"""Run build-tool discovery and BMA400 host regression checks."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


def compiler(variable, candidates):
    if os.environ.get(variable):
        return shlex.split(os.environ[variable])
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return [path]
    raise SystemExit(f"No host {variable} compiler found; no tools were installed.")


def main():
    project = Path(__file__).resolve().parent.parent
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                    "-p", "test_*.py"], cwd=project, check=True)
    cc = compiler("CC", ("clang", "cc", "gcc"))
    cxx = compiler("CXX", ("clang++", "c++", "g++"))
    includes = ["-I" + str(project / "tests/native_stubs"),
                "-I" + str(project / "src/bma400")]
    warnings = ["-Wall", "-Wextra", "-Werror"]
    with tempfile.TemporaryDirectory(prefix="mg24-bma400-test-") as temporary:
        temporary = Path(temporary)
        api_object = temporary / "bma400.o"
        executable = temporary / "bma400_transport_test"
        subprocess.run([*cc, "-std=c99", *warnings, *includes, "-c",
                        str(project / "src/bma400/bma400.c"), "-o", str(api_object)], check=True)
        subprocess.run([*cxx, "-std=c++17", *warnings, *includes,
                        str(project / "src/bma400/Bma400Motion.cpp"),
                        str(project / "tests/bma400_transport_test.cpp"),
                        str(api_object), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
