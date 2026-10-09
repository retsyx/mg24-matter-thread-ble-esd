"""Find installed Silicon Labs packages and their declared executables."""
import os
from pathlib import Path
import re
import subprocess


def package(slt, name, version):
    reference = f'{name}/{version}'
    result = subprocess.run([slt, 'where', reference, '--ignore-slconf'], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    location = result.stdout.strip()
    if result.returncode or not location or not Path(location).is_dir():
        detail = result.stderr.strip()
        raise SystemExit(f'Silicon Labs package {reference} not found via slt. '
                         f'Install it with: slt install {reference}'
                         + (f'\n{detail}' if detail else ''))
    return Path(location).absolute()


def executable(root, name, slt, reference):
    """Use adapter-pack metadata, with the standard bin layout for toolchains.

    Search only inside the SLT-selected package. Environment overrides in legacy
    metadata must not select a tool from a different installation.
    """
    directories = ['.', 'bin']
    names = [name]
    metadata = root / 'apack.json'
    legacy = root / 'apack.info'
    if metadata.is_file():
        result = subprocess.run([slt, 'apack', 'exe', reference, '--exe', name,
                                 '--skip-slconf'], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        location = result.stdout.strip()
        candidate = Path(location)
        if (not result.returncode and location and candidate.is_file()
                and candidate.resolve().is_relative_to(root.resolve())
                and os.access(candidate, os.X_OK)):
            return candidate
        raise SystemExit(f'SLT could not resolve the managed {name} executable in {reference}.'
                         + (f'\n{result.stderr.strip()}' if result.stderr.strip() else ''))
    elif legacy.is_file():
        data = legacy.read_text()
        search_path = re.search(r'^path=(.*)$', data, re.MULTILINE)
        directories = ['.'] + (search_path.group(1).split(',') if search_path else [])
        blocks = re.findall(r'executable\(' + re.escape(name)
                            + r'(?::[^)]*)?\)\s*\{([^}]*)\}', data)
        names = [match.group(1).strip() for block in blocks
                 if (match := re.search(r'^\s*exe=(.+)$', block, re.MULTILINE))]
    matches = {}
    for directory in directories:
        for binary in names:
            if '$' in directory or '$' in binary:
                continue
            candidate = root / directory / binary
            resolved = candidate.resolve()
            if (resolved.is_relative_to(root.resolve()) and candidate.is_file()
                    and os.access(candidate, os.X_OK)):
                matches.setdefault(resolved, candidate)
    if len(matches) != 1:
        raise SystemExit(f'Expected one managed {name} executable in {root}; '
                         f'found {len(matches)}. Check the Silicon Labs package installation.')
    return next(iter(matches.values()))
