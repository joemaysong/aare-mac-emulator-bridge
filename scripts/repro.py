#!/usr/bin/env python3
"""Explicit reproduction steps. doctor has no radio, vehicle or download actions."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import time
import urllib.request
import zipfile

from common import ROOT, CACHE, BRIDGE, LOCK, sdk, jdk, run, digest, asset, adb, require_emulator


def doctor(args):
    java = None
    try: java = str(jdk())
    except RuntimeError: pass
    required = [sdk() / 'platform-tools/adb', sdk() / 'emulator/emulator',
        sdk() / 'build-tools/35.0.0/apksigner', sdk() / 'platforms/android-35/android.jar',
        sdk() / 'system-images/android-35/google_apis/arm64-v8a/package.xml']
    print(json.dumps({'macos': platform.system() == 'Darwin', 'architecture': platform.machine(),
        'java_home_valid': bool(java), 'sdk_root': str(sdk()),
        'missing_android_dependencies': [str(p.relative_to(sdk())) for p in required if not p.exists()],
        'xcrun': bool(shutil.which('xcrun')), 'ffmpeg': bool(shutil.which('ffmpeg')),
        'downloads': False, 'adb_invoked': False, 'radio_changes': False}, indent=2))


def fetch(args):
    target = CACHE / 'downloads'; target.mkdir(parents=True, exist_ok=True)
    source = Path(args.from_cache).expanduser().resolve() if args.from_cache else None
    for name, spec in LOCK['assets'].items():
        output = target / name
        if output.exists() and digest(output) == spec['sha256']:
            print('verified', name); continue
        if source and (source / name).is_file():
            if digest(source / name) != spec['sha256']: raise RuntimeError('cache digest mismatch: ' + name)
            shutil.copyfile(source / name, output); print('copied verified', name); continue
        temporary = output.with_suffix(output.suffix + '.partial')
        with urllib.request.urlopen(urllib.request.Request(spec['url'], headers={'User-Agent': 'aare-mac-emulator-bridge'}), timeout=60) as response, temporary.open('wb') as stream:
            shutil.copyfileobj(response, stream)
        if digest(temporary) != spec['sha256']: raise RuntimeError('download digest mismatch: ' + name)
        temporary.replace(output); print('downloaded and verified', name)


def source_tree():
    target = CACHE / 'upstream' / LOCK['upstream']['commit']
    if target.is_dir(): return target
    staging = target.with_name(target.name + '.extract')
    if staging.exists(): raise RuntimeError('Remove only the incomplete source extraction after inspecting it')
    staging.mkdir(parents=True)
    with tarfile.open(asset('AARE-source.tar.gz')) as archive:
        members = archive.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if not parts or any(x in ('.', '..') for x in parts) or Path(member.name).is_absolute() or not (member.isfile() or member.isdir()):
                raise RuntimeError('unsafe source archive member')
            relative = Path(*parts[1:])
            dest = staging / relative
            if member.isdir(): dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as src, dest.open('wb') as out: shutil.copyfileobj(src, out)
                dest.chmod(0o755 if member.mode & 0o111 else 0o644)
    staging.rename(target)
    return target


def prepare_core(args):
    upstream = source_tree(); target = BRIDGE / 'core'
    if target.exists():
        marker = target / '.integration-source'
        if marker.is_file() and marker.read_text().strip() == LOCK['upstream']['commit']:
            print('Existing generated core retained'); return
        raise RuntimeError('Refuse to overwrite an existing unrecognized core checkout')
    target.mkdir()
    for name in ('aap', 'gradle'):
        shutil.copytree(upstream / name, target / name)
    for name in ('gradlew', 'gradlew.bat', 'gradle.properties', 'LICENSE'):
        shutil.copy2(upstream / name, target / name)
    (target / 'settings.gradle.kts').write_text('''pluginManagement { repositories { gradlePluginPortal(); mavenCentral() } }
dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { mavenCentral() } }
rootProject.name = "AARE-Mac-Core"
include(":aap")
''')
    (target / 'build.gradle.kts').write_text('''plugins {
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.protobuf) apply false
}
''')
    with (target / 'aap/build.gradle.kts').open('a') as stream:
        stream.write('''
// Mac integration: expose the JVM classpath without loading Android Gradle plugins.
val macRuntimeClasspath = sourceSets["main"].runtimeClasspath
tasks.register("writeMacClasspath") {
    dependsOn("classes")
    val target = layout.buildDirectory.file("mac-classpath.txt")
    doLast { target.get().asFile.writeText(macRuntimeClasspath.asPath) }
}
''')
    (target / '.integration-source').write_text(LOCK['upstream']['commit'] + '\n')
    print('Prepared pinned JVM-only core; upstream cache remains unchanged')


def build_core(args):
    target = BRIDGE / 'core'
    if not (target / '.integration-source').is_file(): raise RuntimeError('prepare-core first')
    command = [target / 'gradlew', '-p', target, ':aap:writeMacClasspath', ':aap:test', '--no-daemon', '--no-configuration-cache']
    if args.offline: command += ['--offline']
    run(command, env={**os.environ, 'JAVA_HOME': str(jdk())})


def desktop(args):
    target = CACHE / 'headunit'
    if not target.exists():
        target.mkdir(parents=True)
        with zipfile.ZipFile(asset('aare-headunit-1.1.1.zip')) as archive:
            for name in archive.namelist():
                if Path(name).is_absolute() or '..' in Path(name).parts: raise RuntimeError('unsafe release zip')
            archive.extractall(target)
    libs = target / 'aare-headunit/lib'
    lab = BRIDGE / 'emulator-lab'; build = lab / 'build'; classes = build / 'audio-classes'; classes.mkdir(parents=True, exist_ok=True)
    cp = os.pathsep.join(str(p) for p in sorted(libs.glob('*.jar')))
    run([jdk() / 'bin/javac', '-cp', cp, '-d', classes,
         lab / 'audio-monitor/src/net/prototux/aare/headunit/AudioOutputs.java'])
    overlay = build / 'audio-monitor.jar'
    run([jdk() / 'bin/jar', '--create', '--file', overlay, '-C', classes, '.'])
    inputs = build / 'desktop-input'; inputs.mkdir(exist_ok=True)
    for file in libs.glob('*.jar'): shutil.copy2(file, inputs / file.name)
    shutil.copy2(overlay, inputs / overlay.name)
    manifest = build / 'launcher.MF'
    manifest.write_text('Manifest-Version: 1.0\nMain-Class: net.prototux.aare.headunit.MainKt\nClass-Path: audio-monitor.jar ' + ' '.join(p.name for p in sorted(libs.glob('*.jar'))) + '\n\n')
    empty = build / 'empty'; empty.mkdir(exist_ok=True)
    run([jdk() / 'bin/jar', '--create', '--file', inputs / 'aare-lab-launcher.jar', '--manifest', manifest, '-C', empty, '.'])
    apps = lab / 'apps'; apps.mkdir(exist_ok=True)
    for name, port in [('AARE Desktop', 55277), ('AARE Bridge Desktop', 55278)]:
        output = apps / (name + '.app')
        if output.exists(): raise RuntimeError('Desktop app exists; move the generated app aside before rebuilding')
        run([jdk() / 'bin/jpackage', '--type', 'app-image', '--name', name, '--dest', apps,
            '--input', inputs, '--main-jar', 'aare-lab-launcher.jar', '--main-class', 'net.prototux.aare.headunit.MainKt',
            '--java-options', '-Xmx384m', '--java-options', '-Dsun.java2d.opengl=false',
            '--java-options', '-Daare.lab.evidence=' + str(lab / 'evidence'), '--app-version', '1.1.1',
            '--arguments', f'--host 127.0.0.1 --port {port} --route none --res 1280x720 --serial emulator-5580'])
        run(['codesign', '--force', '--sign', '-', output])
    print('Built local desktop receivers; no emulator or vehicle actions')


def create_avd(args):
    avdmanager = sdk() / 'cmdline-tools/latest/bin/avdmanager'
    home = Path(os.environ.get('ANDROID_AVD_HOME', str(Path.home() / '.android/avd')))
    ini = home / (LOCK['android']['avd'] + '.ini')
    if ini.exists(): raise RuntimeError('Dedicated AVD already exists; refuse to reset user data')
    package = sdk() / 'system-images/android-35/google_apis/arm64-v8a/package.xml'
    if not package.exists(): raise RuntimeError('Install the exact package ID in docs/SETUP.md first; do not substitute Google Play')
    run([avdmanager, 'create', 'avd', '-n', LOCK['android']['avd'], '-k', LOCK['android']['package'], '--device', 'pixel_5'],
        input='no\n', text=True, env={**os.environ, 'JAVA_HOME': str(jdk())})
    config = home / (LOCK['android']['avd'] + '.avd/config.ini')
    values = {'hw.ramSize':'2048', 'hw.cpu.ncore':'2', 'hw.lcd.width':'720', 'hw.lcd.height':'1280',
        'hw.lcd.density':'240', 'hw.gpu.enabled':'yes', 'hw.gpu.mode':'host'}
    lines = [s for s in config.read_text().splitlines() if s.split('=', 1)[0].strip() not in values]
    config.write_text('\n'.join(lines + [f'{k}={v}' for k,v in values.items()]) + '\n')
    record = ROOT / 'build'; record.mkdir(exist_ok=True)
    shutil.copy2(package, record / 'installed-system-image-package.xml')
    print('Created only the dedicated AVD. Installed image revision recorded in build/.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=['doctor', 'fetch', 'prepare-core', 'build-core', 'build-desktop', 'create-avd'])
    parser.add_argument('--from-cache', help='copy only manifest-listed, hash-verified files from an existing cache')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    {'doctor':doctor, 'fetch':fetch, 'prepare-core':prepare_core, 'build-core':build_core,
     'build-desktop':desktop, 'create-avd':create_avd}[args.step](args)


if __name__ == '__main__': main()
