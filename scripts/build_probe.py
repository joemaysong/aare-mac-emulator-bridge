#!/usr/bin/env python3
"""Build the tiny touch-counter / synthetic tone APK using standard Android tools."""
import zipfile
from common import ROOT, BRIDGE, LOCK, sdk, jdk, run, sign_apk


def main():
    root = ROOT / 'build/probe'
    platform = sdk() / 'platforms/android-35/android.jar'
    if not platform.is_file(): raise RuntimeError('Install platforms;android-35 before building the optional probe APK')
    if root.exists(): raise RuntimeError('Move the existing generated build/probe aside before rebuilding')
    classes = root / 'classes'; classes.mkdir(parents=True)
    tools = sdk() / 'build-tools' / LOCK['android']['build_tools']
    source = BRIDGE / 'emulator-lab/audio-probe/src/org/ev6/aarelab/MainActivity.java'
    run([jdk() / 'bin/javac', '-source', '8', '-target', '8', '-bootclasspath', platform, '-d', classes, source])
    jar = root / 'probe-classes.jar'; run([jdk() / 'bin/jar', '--create', '--file', jar, '-C', classes, '.'])
    run([tools / 'd8', '--min-api', '19', '--lib', platform, '--output', root, jar])
    manifest = root / 'AndroidManifest.xml'
    manifest.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.ev6.aarelab" android:versionCode="1" android:versionName="1.0">
 <uses-sdk android:minSdkVersion="19" android:targetSdkVersion="35"/>
 <application android:label="AARE Lab" android:theme="@android:style/Theme.Material.NoActionBar" android:allowBackup="false">
  <activity android:name=".MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity>
 </application></manifest>''')
    unsigned = root / 'probe-unsigned.apk'
    run([tools / 'aapt2', 'link', '-I', platform, '--manifest', manifest, '-o', unsigned])
    with zipfile.ZipFile(unsigned, 'a') as archive: archive.write(root / 'classes.dex', 'classes.dex')
    sign_apk(unsigned, root / 'AARE-Lab.apk')
    print('Built synthetic test APK. Not installed or launched.')


if __name__ == '__main__': main()
