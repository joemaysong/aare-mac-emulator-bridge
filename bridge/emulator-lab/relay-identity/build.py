"""Patch the exact retained AARE lab APK; preserve encoder fix and signer, never install."""
from pathlib import Path
import subprocess,json,hashlib,zipfile,re,sys,os,argparse
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'scripts'))
from common import ROOT,BRIDGE,LOCK,asset,jdk,sdk,sign_apk
from normalize_smali import normalize
out=ROOT/'build/relay-identity'
if out.exists():raise RuntimeError('Move the previous build/relay-identity aside before rebuilding')
base=ROOT/'build/apk-patch/aare-emulator.apk'
proof=json.loads((base.parent/'verification.json').read_text())
sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
if sha(base)!=proof['patched_apk_sha256'] or proof['original_apk_sha256']!=LOCK['assets']['aare-1.1.1.apk']['sha256']:
 raise RuntimeError('Pinned emulator patch input mismatch')
java=jdk()/'bin/java';android=sdk()/'platforms/android-35/android.jar'
if not android.is_file():raise RuntimeError('Install platforms;android-35')
cp=':'.join(str(asset(n)) for n in LOCK['assets'] if n.endswith('.jar'))
out.mkdir(parents=True)
def run(cmd,name,env=None):
 x=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,timeout=120,env=env);(out/(name+'.log')).write_text(x.stdout+x.stderr);x.check_returncode();return x.stdout
source=HERE/'src/org/ev6/aare/RelayIdentity.java';tests=sorted((HERE/'test').rglob('*.java'))
classes=out/'test-classes';classes.mkdir()
run([jdk()/'bin/javac','-source','8','-target','8','-d',classes,source,*tests],'test-compile')
result=run([java,'-cp',classes,'org.ev6.aare.RelayIdentityTest',out/'fixture'],'test')
classes=out/'classes';classes.mkdir()
run([jdk()/'bin/javac','-source','8','-target','8','-bootclasspath',android,'-d',classes,source],'compile')
dex=out/'dex';dex.mkdir()
run([java,'-cp',sdk()/'build-tools'/LOCK['android']['build_tools']/'lib/d8.jar','com.android.tools.r8.D8','--min-api','26','--lib',android,'--output',dex,*classes.rglob('*.class')],'helper-d8')
def contract(directory):
 return {p.relative_to(directory).as_posix():hashlib.sha256(('\n'.join(normalize(p.read_text()))+'\n').encode()).hexdigest() for p in sorted(directory.rglob('*.smali'))}
with zipfile.ZipFile(base) as z:(out/'baseline.dex').write_bytes(z.read('classes4.dex'))
tree=out/'smali';run([java,'-cp',cp,'org.jf.baksmali.Main','d','-a','26',out/'baseline.dex','-o',tree],'disassemble')
before=contract(tree)
rel='net/prototux/aare/car/CarSession.smali';f=tree/rel;s=f.read_text();s=s.replace('.field private encoder:Lnet/prototux/aare/video/VideoEncoder;', '.field private encoder:Lnet/prototux/aare/video/VideoEncoder;\n\n.field private ev6RelayIdentity:Ljava/lang/Object;')
anchor='    iput-object v2, v0, Lnet/prototux/aare/car/CarSession;->context:Landroid/content/Context;';assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\n\n    invoke-static {v2, v13, v14}, Lorg/ev6/aare/RelayIdentity;->capture(Landroid/content/Context;ZLjava/lang/String;)Ljava/lang/Object;\n    move-result-object v6\n    iput-object v6, v0, Lnet/prototux/aare/car/CarSession;->ev6RelayIdentity:Ljava/lang/Object;')
anchor='    invoke-direct {v3, v4, v5}, Lnet/prototux/aare/aap/channels/BluetoothChannel;-><init>(Laap_protobuf/service/ServiceOuterClass$Service;Lnet/prototux/aare/aap/channels/BluetoothChannel$Listener;)V';assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\n\n    iget-object v4, p0, Lnet/prototux/aare/car/CarSession;->ev6RelayIdentity:Ljava/lang/Object;\n    invoke-static {v4, v3}, Lorg/ev6/aare/RelayIdentity;->bind(Ljava/lang/Object;Ljava/lang/Object;)V')
anchor='.method public onRunning(Lnet/prototux/aare/aap/AapSession;)V\n    .registers 3';assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\n\n    iget-object v0, p0, Lnet/prototux/aare/car/CarSession;->ev6RelayIdentity:Ljava/lang/Object;\n    invoke-static {v0}, Lorg/ev6/aare/RelayIdentity;->running(Ljava/lang/Object;)V');f.write_text(s)
listener='net/prototux/aare/car/CarSession$onServiceDiscovery$12.smali';f=tree/listener;s=f.read_text();anchor='    invoke-super {p0, p1, p2}, Lnet/prototux/aare/aap/channels/BluetoothChannel$Listener;->onPairingResponse(ZZ)V';assert s.count(anchor)==1;s=s.replace(anchor,anchor+'\n\n    invoke-static {p1, p2}, Lorg/ev6/aare/RelayIdentity;->response(ZZ)V');f.write_text(s)
run([java,'-cp',cp,'org.jf.baksmali.Main','d','-a','26',dex/'classes.dex','-o',out/'helper-smali'],'helper-disassemble')
for f in (out/'helper-smali').rglob('*.smali'):
 target=tree/f.relative_to(out/'helper-smali');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(f.read_bytes())
after=contract(tree);changed=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k));assert changed==sorted([rel,listener,'org/ev6/aare/RelayIdentity.smali']),changed
run([java,'-cp',cp,'org.jf.smali.Main','a','-a','26','-j','1',tree,'-o',out/'classes4.dex'],'assemble')
run([java,'-cp',cp,'org.jf.baksmali.Main','d','-a','26',out/'classes4.dex','-o',out/'roundtrip'],'roundtrip');assert after==contract(out/'roundtrip')
with zipfile.ZipFile(base) as z,zipfile.ZipFile(out/'unsigned.apk','w') as w:
 for info in z.infolist():
  if info.filename.startswith('META-INF/') and (info.filename.endswith(('.SF','.RSA','.DSA','.EC')) or info.filename=='META-INF/MANIFEST.MF'):continue
  w.writestr(info,(out/'classes4.dex').read_bytes() if info.filename=='classes4.dex' else z.read(info.filename))
sign_apk(out/'unsigned.apk',out/'aare-relay.apk')
(out/'verification.json').write_text(json.dumps(dict(base_sha256=sha(base),apk_sha256=sha(out/'aare-relay.apk'),tests=result.strip(),canonical_roundtrip=True,signer_preserved=True,signer_scope="checkout local key; not the original author or private vehicle lab",changed_classes=changed,source_sha256={str(source.relative_to(ROOT)):sha(source),str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},installed=False,vehicle_verified=False),indent=2)+'\n');print(result.strip());print('AARE_RELAY_IDENTITY_BUILT_NOT_INSTALLED')
