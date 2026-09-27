"""Build an isolated debug APK using locally installed Android build tools.

No Gradle download or production-app changes. All output stays in .local-data.
"""
from pathlib import Path
import os
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATA = ROOT / '.local-data' / 'amap-sdk'
SDK = Path(os.environ.get('AMAP_PROBE_ANDROID_SDK', DATA / 'android-sdk'))
OUT = DATA / 'probe-build'
BUILD = SDK / 'build-tools' / '33.0.2'
ANDROID = SDK / 'platforms' / 'android-33' / 'android.jar'
JAR = next((DATA / 'unpacked').glob('*.jar'))
EXE = '.exe' if os.name == 'nt' else ''


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


OUT.mkdir(parents=True, exist_ok=True)
classes = OUT / 'classes'
dex = OUT / 'dex'
classes.mkdir(exist_ok=True)
dex.mkdir(exist_ok=True)
run('javac', '-encoding', 'UTF-8', '-source', '8', '-target', '8',
    '-classpath', os.pathsep.join(map(str, [ANDROID, JAR])), '-d', classes,
    *HERE.glob('src/**/*.java'))
with zipfile.ZipFile(OUT / 'probe-classes.jar', 'w') as archive:
    for item in classes.rglob('*.class'):
        archive.write(item, item.relative_to(classes).as_posix())
run('java', '-Xmx2g', '-cp', BUILD / 'lib' / 'd8.jar', 'com.android.tools.r8.D8',
    '--min-api', '23', '--lib', ANDROID, '--output', dex, OUT / 'probe-classes.jar', JAR)
apk = OUT / 'unsigned.apk'
run(BUILD / ('aapt' + EXE), 'package', '-f', '-M', HERE / 'AndroidManifest.xml', '-I', ANDROID, '-F', apk)
with zipfile.ZipFile(apk, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
    for item in dex.glob('*.dex'):
        archive.write(item, item.name)
    with zipfile.ZipFile(JAR) as sdkjar:
        for name in sdkjar.namelist():
            if name.startswith('assets/') and not name.endswith('/'):
                archive.writestr(name, sdkjar.read(name))
    for item in (DATA / 'unpacked' / 'arm64-v8a').glob('*.so'):
        archive.write(item, 'lib/arm64-v8a/' + item.name)
key = OUT / 'debug.keystore'
if not key.exists():
    run('keytool', '-genkeypair', '-keystore', key, '-storepass', 'android', '-keypass', 'android',
        '-alias', 'androiddebugkey', '-dname', 'CN=AMap Local Probe', '-keyalg', 'RSA', '-validity', '3650')
aligned = OUT / 'aligned.apk'
run(BUILD / ('zipalign' + EXE), '-f', '4', apk, aligned)
signed = OUT / 'amap-probe.apk'
run('java', '-jar', BUILD / 'lib' / 'apksigner.jar', 'sign', '--ks', key,
    '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', signed, aligned)
run('java', '-jar', BUILD / 'lib' / 'apksigner.jar', 'verify', '--print-certs', signed)
print('APK:', signed)
