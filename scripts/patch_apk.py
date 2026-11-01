#!/usr/bin/env python3
"""Hash-gated v1.1.1 emulator-only patch; never installs on any device."""
import json
from pathlib import Path
import shutil
import zipfile
from common import ROOT, CACHE, BRIDGE, LOCK, jdk, run, asset, digest, sign_apk


def main():
    original = asset('aare-1.1.1.apk')
    work = ROOT / 'build/apk-patch'
    if work.exists(): raise RuntimeError('Patch work exists; move build/apk-patch aside before rerunning')
    work.mkdir(parents=True)
    tools = [asset(n) for n in LOCK['assets'] if n.endswith('.jar')]
    cp = ':'.join(map(str, tools)); java = jdk() / 'bin/java'
    with zipfile.ZipFile(original) as archive:
        dex = archive.read('classes4.dex'); (work / 'classes4.dex').write_bytes(dex)
    smali = work / 'smali'
    run([java, '-cp', cp, 'org.jf.baksmali.Main', 'disassemble', work / 'classes4.dex', '-o', smali])
    file = smali / 'net/prototux/aare/video/VideoEncoder.smali'
    text = file.read_text()
    marker = '    invoke-virtual {v3}, Landroid/media/MediaCodec;->reset()V'
    if text.count(marker) != 1 or '.method public final start()V\n    .registers 14' not in text:
        raise RuntimeError('Pinned release smali shape changed; no patch applied')
    original_text = text
    addition = '''
    # Emulator compatibility: MediaCodec.reset clears its asynchronous callback.
    new-instance v8, Lnet/prototux/aare/video/VideoEncoder$Callback;
    invoke-direct {v8, p0}, Lnet/prototux/aare/video/VideoEncoder$Callback;-><init>(Lnet/prototux/aare/video/VideoEncoder;)V
    new-instance v10, Landroid/os/Handler;
    invoke-virtual {v2}, Landroid/os/HandlerThread;->getLooper()Landroid/os/Looper;
    move-result-object v12
    invoke-direct {v10, v12}, Landroid/os/Handler;-><init>(Landroid/os/Looper;)V
    invoke-virtual {v3, v8, v10}, Landroid/media/MediaCodec;->setCallback(Landroid/media/MediaCodec$Callback;Landroid/os/Handler;)V
'''
    file.write_text(text.replace(marker, marker + '\n' + addition))
    (work / 'VideoEncoder.smali.original').write_text(original_text)
    run([java, '-cp', cp, 'org.jf.smali.Main', 'assemble', smali, '-o', work / 'patched.dex'])
    unsigned = work / 'aare-emulator-unsigned.apk'
    changed = []
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(unsigned, 'w') as target:
        for info in source.infolist():
            if info.filename.startswith('META-INF/'): continue
            value = source.read(info.filename)
            if info.filename == 'classes4.dex': value = (work / 'patched.dex').read_bytes(); changed.append(info.filename)
            target.writestr(info, value)
    # Check all other content, including all other DEX files and Android resources.
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(unsigned) as target:
        for name in target.namelist():
            if name != 'classes4.dex' and source.read(name) != target.read(name): raise RuntimeError('unexpected APK change')
    output = work / 'aare-emulator.apk'; sign_apk(unsigned, output)
    (work / 'verification.json').write_text(json.dumps({'original_apk_sha256': digest(original),
        'patched_apk_sha256': digest(output), 'changed_content_entries': changed,
        'signature':'new local debug key; not original AARE signer', 'installed':False,
        'upstream':LOCK['upstream'], 'source_equivalent_patch':'patches/VideoEncoder.compat.patch'}, indent=2) + '\n')
    print('Built', output)
    print('No install performed; signatures differ, so an existing upstream install cannot be overwritten.')


if __name__ == '__main__': main()
