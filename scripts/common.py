from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
BRIDGE = ROOT / 'bridge'
LOCK = json.loads((ROOT / 'dependencies.lock.json').read_text())


def sdk():
    return Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Library/Android/sdk'))).expanduser().resolve()


def jdk():
    value = os.environ.get('JAVA_HOME')
    if not value:
        raise RuntimeError('Set JAVA_HOME to a full JDK 17 or 21. See docs/SETUP.md.')
    path = Path(value).expanduser().resolve()
    for binary in ('java', 'javac', 'jar', 'keytool', 'jpackage'):
        if not (path / 'bin' / binary).is_file():
            raise RuntimeError('A full JDK with javac and jpackage is required')
    return path


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset(name):
    path = CACHE / 'downloads' / name
    if not path.is_file() or digest(path) != LOCK['assets'][name]['sha256']:
        raise RuntimeError(f'Missing or mismatched {name}; run scripts/repro.py fetch')
    return path


def adb(*args, capture=False):
    prefix = [sdk() / 'platform-tools/adb', '-s', LOCK['android']['serial']]
    if capture:
        return subprocess.check_output([str(x) for x in [*prefix, *args]], text=True, timeout=15).strip()
    return run([*prefix, *args], timeout=20)


def require_emulator():
    if adb('emu', 'avd', 'name', capture=True).splitlines()[0].strip() != LOCK['android']['avd']:
        raise RuntimeError('The dedicated AARE AVD is not running on emulator-5580')
    if adb('shell', 'getprop', 'sys.boot_completed', capture=True).strip() != '1':
        raise RuntimeError('Wait for the dedicated AVD to finish booting')


def signing_key():
    key = CACHE / 'signing' / 'emulator-debug.jks'
    key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not key.exists():
        run([jdk() / 'bin/keytool', '-genkeypair', '-keystore', key, '-storepass', 'android',
             '-keypass', 'android', '-alias', 'emulator-debug', '-keyalg', 'RSA', '-keysize', '2048',
             '-validity', '3650', '-dname', 'CN=AARE Emulator Local Debug', '-noprompt'],
             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        key.chmod(0o600)
    return key


def sign_apk(unsigned, output):
    tools = sdk() / 'build-tools' / LOCK['android']['build_tools']
    aligned = Path(unsigned).with_suffix('.aligned.apk')
    run([tools / 'zipalign', '-f', '-p', '4', unsigned, aligned])
    run([tools / 'apksigner', 'sign', '--ks', signing_key(), '--ks-key-alias', 'emulator-debug',
         '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', output, aligned],
        env={**os.environ, 'JAVA_HOME': str(jdk())})
    run([tools / 'apksigner', 'verify', output], env={**os.environ, 'JAVA_HOME': str(jdk())})
