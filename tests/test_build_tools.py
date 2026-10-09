"""Check that build tools come only from the package selected by SLT."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


HELPER = Path(__file__).resolve().parents[1] / "scripts" / "silabs_tools.py"
SPEC = importlib.util.spec_from_file_location("silabs_tools", HELPER)
tools = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tools)


class PackageLookupTest(unittest.TestCase):
    def test_asks_slt_for_the_exact_package_version(self):
        with tempfile.TemporaryDirectory(prefix="mg24-package-") as directory:
            response = subprocess.CompletedProcess([], 0, directory + "\n", "")
            with patch.object(tools.subprocess, "run", return_value=response) as run:
                found = tools.package("/tools/slt", "cmake", "3.30.2")
            self.assertEqual(found, Path(directory).absolute())
            run.assert_called_once_with(
                ["/tools/slt", "where", "cmake/3.30.2", "--ignore-slconf"], text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_empty_lookup_explains_how_to_install_the_package(self):
        response = subprocess.CompletedProcess([], 0, "\n", "")
        with patch.object(tools.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(SystemExit, "slt install cmake/3.30.2"):
                tools.package("slt", "cmake", "3.30.2")

    def test_nonexistent_location_is_not_accepted(self):
        with tempfile.TemporaryDirectory(prefix="mg24-package-") as directory:
            response = subprocess.CompletedProcess([], 0, directory + "/missing\n", "")
            with patch.object(tools.subprocess, "run", return_value=response):
                with self.assertRaisesRegex(SystemExit, "not found via slt"):
                    tools.package("slt", "cmake", "3.30.2")

    def test_file_location_is_not_a_package_directory(self):
        with tempfile.TemporaryDirectory(prefix="mg24-package-") as directory:
            location = Path(directory) / "not-a-directory"
            location.touch()
            response = subprocess.CompletedProcess([], 0, str(location), "")
            with patch.object(tools.subprocess, "run", return_value=response):
                with self.assertRaisesRegex(SystemExit, "not found via slt"):
                    tools.package("slt", "cmake", "3.30.2")

    def test_failed_lookup_preserves_slt_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix="mg24-package-") as directory:
            response = subprocess.CompletedProcess(
                [], 1, directory, "Requested package version is not installed\n")
            with patch.object(tools.subprocess, "run", return_value=response):
                with self.assertRaisesRegex(SystemExit, "Requested package version is not installed"):
                    tools.package("slt", "cmake", "3.30.2")


class ExecutableLookupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mg24-tools-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "package"
        self.root.mkdir()

    def binary(self, relative, executable=True):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755 if executable else 0o644)
        return path

    def metadata(self, paths, executables):
        (self.root / "apack.json").write_text(json.dumps({
            "path": paths, "executable": executables,
        }))

    def legacy_metadata(self, text):
        (self.root / "apack.info").write_text(text)

    def lookup(self, name):
        return tools.executable(self.root, name, "/tools/slt", "package/1.0")

    def response(self, path, returncode=0, stderr=""):
        return subprocess.CompletedProcess([], returncode, str(path) + "\n", stderr)

    def test_toolchain_without_metadata_uses_bin(self):
        compiler = self.binary("bin/arm-none-eabi-gcc")
        self.assertEqual(self.lookup("arm-none-eabi-gcc"), compiler)

    def test_package_root_layout_is_supported(self):
        ninja = self.binary("ninja")
        self.assertEqual(self.lookup("ninja"), ninja)

    def test_legacy_metadata_finds_linux_layout(self):
        cmake = self.binary("linux_x86_64/bin/cmake")
        self.legacy_metadata(
            "path=.,bin,linux_aarch64/bin,linux_x86_64/bin\n"
            "executable(cmake:linux.x86_64) {\n  exe=cmake\n}\n"
            "executable(cmake:linux.aarch64) {\n  exe=cmake\n}\n"
            "executable(cmake:win32.x86_64) {\n  exe=cmake.exe\n}\n")
        self.assertEqual(self.lookup("cmake"), cmake)

    def test_gui_with_same_filename_outside_declared_path_is_ignored(self):
        cmake = self.binary("tools/bin/cmake")
        self.binary("tools/gui/cmake")
        self.legacy_metadata(
            "path=tools/bin\n"
            "executable(cmake:linux.x86_64) {\n  exe=cmake\n}\n")
        self.assertEqual(self.lookup("cmake"), cmake)

    def test_json_metadata_supports_nested_linux_executable(self):
        python = self.binary("bin/python3")
        self.metadata([".", "bin"], {
            "python:linux.x86_64": {"exe": "bin/python3"},
            "python:linux.aarch64": {"exe": "bin/python3"},
            "python:win32.x86_64": {"exe": "python.exe"},
        })
        with patch.object(tools.subprocess, "run", return_value=self.response(python)) as run:
            self.assertEqual(self.lookup("python"), python)
        run.assert_called_once_with(
            ["/tools/slt", "apack", "exe", "package/1.0", "--exe", "python", "--skip-slconf"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_json_delegates_platform_selection_to_slt(self):
        slc = self.binary("slc")
        self.binary("slc.bat")
        self.metadata(["."], {
            "slc:linux.x86_64": {"exe": "slc"},
            "slc:win32.x86_64": {"exe": "slc.bat"},
        })
        with patch.object(tools.subprocess, "run", return_value=self.response(slc)):
            self.assertEqual(self.lookup("slc"), slc)

    def test_json_resolution_failure_preserves_slt_diagnostic(self):
        self.metadata(["."], {"zap-cli": {"exe": "zap-cli"}})
        response = self.response("", 1, "No native executable for this platform")
        with patch.object(tools.subprocess, "run", return_value=response):
            with self.assertRaisesRegex(SystemExit, "No native executable for this platform"):
                self.lookup("zap-cli")

    def test_json_resolution_cannot_select_an_external_executable(self):
        outside = self.directory / "external-cmake"
        outside.write_text("#!/bin/sh\nexit 0\n")
        outside.chmod(0o755)
        self.metadata(["."], {"cmake": {"exe": "cmake"}})
        with patch.object(tools.subprocess, "run", return_value=self.response(outside)):
            with self.assertRaises(SystemExit):
                self.lookup("cmake")

    def test_json_resolution_requires_an_existing_executable_file(self):
        self.metadata(["."], {"cmake": {"exe": "cmake"}})
        not_executable = self.binary("cmake", executable=False)
        for location in (self.root / "missing", not_executable, self.root):
            with self.subTest(location=location):
                with patch.object(tools.subprocess, "run", return_value=self.response(location)):
                    with self.assertRaises(SystemExit):
                        self.lookup("cmake")

    def test_repeated_paths_and_symlink_aliases_are_one_executable(self):
        ninja = self.binary("bin/ninja")
        (self.root / "ninja").symlink_to(ninja.relative_to(self.root))
        self.legacy_metadata(
            "path=.,bin,bin\n"
            "executable(ninja:linux.x86_64) {\n  exe=ninja\n}\n"
            "executable(ninja:linux.aarch64) {\n  exe=ninja\n}\n")
        self.assertEqual(self.lookup("ninja").resolve(), ninja.resolve())

    def test_environment_override_paths_do_not_select_unmanaged_tools(self):
        cmake = self.binary("bin/cmake")
        outside = self.directory / "external"
        outside.mkdir()
        (outside / "cmake").write_text("#!/bin/sh\nexit 0\n")
        (outside / "cmake").chmod(0o755)
        self.legacy_metadata(
            "path=$(env.STUDIO_CMAKE_PATH),$(env.STUDIO_CMAKE_PATH)/bin,bin\n"
            "executable(cmake:linux.x86_64) {\n  exe=cmake\n}\n")
        with patch.dict(tools.os.environ, {"STUDIO_CMAKE_PATH": str(outside)}):
            self.assertEqual(self.lookup("cmake"), cmake)

    def test_metadata_cannot_escape_the_selected_package(self):
        outside = self.directory / "external"
        outside.mkdir()
        binary = outside / "cmake"
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        for directory in (str(outside), "../external"):
            with self.subTest(directory=directory):
                self.legacy_metadata(
                    f"path={directory}\n"
                    "executable(cmake:linux.x86_64) {\n  exe=cmake\n}\n")
                with self.assertRaisesRegex(SystemExit, "found 0"):
                    self.lookup("cmake")

    def test_symlink_to_external_tool_is_not_accepted(self):
        outside = self.directory / "external-cmake"
        outside.write_text("#!/bin/sh\nexit 0\n")
        outside.chmod(0o755)
        (self.root / "cmake").symlink_to(outside)
        with self.assertRaisesRegex(SystemExit, "found 0"):
            self.lookup("cmake")

    def test_executable_environment_expression_is_not_expanded(self):
        self.binary("bin/cmake")
        self.legacy_metadata(
            "path=bin\n"
            "executable(cmake:linux.x86_64) {\n  exe=$(env.CMAKE)\n}\n")
        with self.assertRaisesRegex(SystemExit, "found 0"):
            self.lookup("cmake")

    def test_missing_executable_reports_package_installation_problem(self):
        with self.assertRaisesRegex(SystemExit, "found 0.*Check the Silicon Labs package"):
            self.lookup("cmake")

    def test_nonexecutable_file_is_not_accepted(self):
        self.binary("bin/cmake", executable=False)
        with self.assertRaisesRegex(SystemExit, "found 0"):
            self.lookup("cmake")

    def test_ambiguous_executables_fail_instead_of_selecting_arbitrarily(self):
        self.binary("cmake")
        self.binary("bin/cmake")
        with self.assertRaisesRegex(SystemExit, "found 2"):
            self.lookup("cmake")


if __name__ == "__main__":
    unittest.main()
