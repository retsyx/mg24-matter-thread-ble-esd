#!/usr/bin/env python3
"""Generate platform and Matter inputs with existing Silicon Labs packages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


PLATFORM_FILES = (
    'RTE_Components.h', 'gatt_db.c', 'gatt_db.h', 'gen.properties',
    'linkerfile.ld', 'sl_application_type.h', 'sl_bluetooth.c', 'sl_bluetooth.h',
    'sl_component_catalog.h', 'sl_event_handler.c', 'sl_event_handler.h',
    'sl_iostream_handles.c', 'sl_iostream_handles.h',
    'sl_iostream_init_instances.h', 'sl_ot_custom_cli.c', 'sl_ot_init.c',
    'sl_ot_init.h', 'sl_simple_led_instances.c', 'sl_simple_led_instances.h',
    'sl_uartdrv_init.c', 'sl_uartdrv_instances.h', 'sli_mbedtls_config_autogen.h',
    'sli_mbedtls_config_transform_autogen.h', 'sli_psa_builtin_config_autogen.h',
    'sli_psa_config_autogen.h',
)
MATTER_FILES = (
    'app/callback-stub.cpp', 'app/cluster-init-callback.cpp',
    'attributes/Accessors.cpp', 'cluster-objects.cpp', 'IMClusterCommandHandler.cpp',
    'app/PluginApplicationCallbacks.h', 'endpoint_config.h', 'gen_config.h',
    'access.h', 'app-common/zap-generated/attributes/Accessors.h',
)


def source_hashes(project):
    files = [project] + sorted(p for p in (project.parent / 'config').rglob('*') if p.is_file())
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def run_generator(command, env, log):
    result = subprocess.run(command, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_text(result.stdout)
    if result.returncode:
        print('\n'.join(result.stdout.splitlines()[-40:]))
        raise SystemExit(f'Generation failed with exit {result.returncode}; see {log}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('slc', 'java', 'python', 'python-executable', 'sdk', 'matter',
                 'gcc', 'gcc-executable', 'zap', 'zap-cli', 'project', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    paths = {name: value.resolve() for name, value in vars(args).items()}
    project = paths['project']
    output = paths['output']
    if output == project.parent or output in project.parent.parents:
        raise SystemExit('The generation output must be separate from the source project.')
    before = source_hashes(project)
    slc_jar = paths['slc'].parent / 'slc.jar'
    if not slc_jar.is_file():
        raise SystemExit(f'The standalone Silicon Labs SLC package is missing {slc_jar}.')
    state = output / '.slc-state'
    (state / 'home').mkdir(parents=True, exist_ok=True)

    # SLC and its adapter packs may upgrade their working project. Generate from
    # a snapshot so the manifest and authoritative configuration stay untouched.
    snapshot = state / 'project'
    if snapshot.exists():
        shutil.rmtree(snapshot)
    snapshot.mkdir()
    ignore = shutil.ignore_patterns('slc_args.json', '__pycache__', '*.pyc')
    for name in ('src', 'include', 'config', 'linker_options'):
        source = project.parent / name
        if source.is_dir():
            shutil.copytree(source, snapshot / name, ignore=ignore)
    shutil.copy2(project, snapshot / project.name)
    for name in ('README.md', 'LICENSE', 'main.c'):
        source = project.parent / name
        if source.is_file():
            shutil.copy2(source, snapshot / name)
    if (output / 'config').exists():
        shutil.rmtree(output / 'config')
    shutil.copytree(project.parent / 'config', output / 'config', ignore=ignore)
    if (output / 'autogen').exists():
        shutil.rmtree(output / 'autogen')

    env = dict(os.environ, STUDIO_PYTHON3_PATH=str(paths['python']),
               PYTHONDONTWRITEBYTECODE='1', ZAP_TEMPSTATE='1',
               ZAP_SKIP_POST_GENERATION='1')
    env['PATH'] = os.pathsep.join([
        str(paths['java'].parent), str(paths['python_executable'].parent),
        str(paths['gcc_executable'].parent), env.get('PATH', ''),
    ])
    env['JAVA_HOME'] = str(paths['java'].parent.parent)
    # SLC starts a second JVM. Apply the isolated home to both JVMs so its
    # configuration, component cache and workspace stay inside the build.
    env['JAVA_TOOL_OPTIONS'] = '-Duser.home="' + str(state / 'home') + '"'
    packs = (paths['python'], paths['sdk'] / 'protocol/bluetooth/bin/gatt',
             paths['matter'] / 'provision', paths['zap'])
    # The standalone SLC package documents java -jar slc.jar as its supported
    # interface for selecting Java explicitly, alongside the slc wrapper.
    command = [
        str(paths['java']), '-jar', str(slc_jar),
        '--no-daemon', '--ignore-slt', '-data', str(state / 'workspace'), 'generate',
        '--sdk-package-path=' + str(paths['sdk']) + ',' + str(paths['matter']),
        '-p', str(snapshot / project.name), '-d', str(output), '-o', 'cmake',
        '--no-copy', '--generator-timeout=180',
        '--toolchain-locations=gcc:' + str(paths['gcc_executable']),
        '--tool-path=' + ','.join(map(str, packs)),
    ]
    (state / 'slc-command.json').write_text(json.dumps(command, indent=2))
    run_generator(command, env, state / 'slc.log')

    # The stock SLC adapter upgrades its working ZAP model. Regenerate from the
    # authoritative original with the same direct command used by native builds.
    generated = output / 'autogen/zap-generated'
    if generated.exists():
        shutil.rmtree(generated)
    generated.mkdir(parents=True)
    templates = paths['matter'] / 'src/app/zap-templates'
    command = [
        str(paths['zap_cli']), 'generate', '--noUi', '--noServer',
        '--tempState', '--skipPostGeneration',
        '-i', str(project.parent / 'config/common/mailbox-motion.zap'),
        '-z', str(templates / 'zcl/zcl.json'),
        '-g', str(templates / 'app-templates.json'), '-o', str(generated),
    ]
    (state / 'zap-command.json').write_text(json.dumps(command, indent=2))
    run_generator(command, env, state / 'zap.log')
    if source_hashes(project) != before:
        raise SystemExit('Source manifest/configuration changed during generation; rebuild with the current inputs.')
    missing = [name for name in PLATFORM_FILES if not (output / 'autogen' / name).is_file()]
    missing += ['zap-generated/' + name for name in MATTER_FILES if not (generated / name).is_file()]
    if missing:
        raise SystemExit('Missing generated inputs: ' + ', '.join(missing))
    print('Generated Silicon Labs platform and Matter inputs from the project configuration.')


if __name__ == '__main__':
    main()
