#!/usr/bin/env python3
"""Create an optional local Magisk module; no download, ADB or installation."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from common import ROOT

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--apk', type=Path, required=True)
p.add_argument('--sha256', required=True)
a = p.parse_args()
data = a.apk.read_bytes()
if hashlib.sha256(data).hexdigest() != a.sha256:
    raise RuntimeError('Retained APK hash mismatch')
with zipfile.ZipFile(a.apk) as z:
    if z.testzip() is not None or 'AndroidManifest.xml' not in z.namelist():
        raise RuntimeError('Invalid APK container')
out = ROOT / 'build/privileged-module'
if out.exists():
    raise RuntimeError('Move existing build/privileged-module aside before rebuilding')
out.mkdir(parents=True)
prop = '''id=aare
name=AARE (privileged emulator lab)
version=1.1.1-lab
versionCode=10101
author=prototux and AARE contributors; local integration
 description=Local retained AARE APK with privileged audio permissions.
'''.replace('\n description=', '\ndescription=')
permissions = '''<?xml version="1.0" encoding="utf-8"?>
<permissions><privapp-permissions package="net.prototux.aare">
<permission name="android.permission.MODIFY_AUDIO_ROUTING" />
<permission name="android.permission.CAPTURE_AUDIO_OUTPUT" />
</privapp-permissions></permissions>
'''
with zipfile.ZipFile(out/'aare-lab-magisk.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('module.prop', prop)
    z.writestr('system/priv-app/AARE/AARE.apk', data)
    z.writestr('system/etc/permissions/privapp-permissions-aare.xml', permissions)
(out/'verification.json').write_text(json.dumps({'input_apk_sha256':a.sha256,
    'module_sha256':hashlib.sha256((out/'aare-lab-magisk.zip').read_bytes()).hexdigest(),
    'installed':False, 'requires_user_verified_package_and_retained_signer':True}, indent=2)+'\n')
print('Local module built. Verify APK package and signer independently; no install performed.')
