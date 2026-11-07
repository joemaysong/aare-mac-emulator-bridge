"""Passive Mac Bluetooth inventory. No scan, pairing, RFCOMM, Wi-Fi or projection effects."""
from pathlib import Path
import json,subprocess,tempfile,time
import run_session

def readiness(report,target,now):
    rows=report.get('events',[])
    if len(rows)!=1 or rows[0].get('event')!='pairing_state':return 'unknown'
    row=rows[0]
    if row.get('target')!=target.lower().replace(':','-'):return 'unknown'
    uptime=row.get('uptime')
    if not isinstance(uptime,(float,int)) or not 0<=now-uptime<=8:return 'unknown'
    if type(row.get('powered')) is not bool or type(row.get('paired')) is not bool:return 'unknown'
    if not row['powered']:return 'waiting_bluetooth'
    if not row['paired']:return 'waiting_pairing'
    return 'ready'

class PairingWatch:
    def __init__(self,target):
        self.target=target;self.tmp=None;self.child=None
    def __enter__(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='aare-pairing-');self.report=Path(self.tmp.name)/'state.json'
        app=run_session.ROOT/'build/AARE Mac Probe.app'
        if not app.is_dir():self.tmp.cleanup();raise RuntimeError('Pairing watcher app missing')
        self.child=subprocess.Popen(['open','-n','-W',str(app),'--args','--watch-pairing','--device',self.target,'--output',str(self.report)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return self
    def state(self):
        if self.child.poll() is not None:raise RuntimeError('Pairing inventory process stopped')
        try:return readiness(json.loads(self.report.read_text()),self.target,time.monotonic())
        except (FileNotFoundError,ValueError):return 'unknown'
    def __exit__(self,*exc):
        # A private stop file is interpreted only by this exact inventory instance.
        (self.report.parent/'stop').touch()
        try:self.child.wait(timeout=6)
        except subprocess.TimeoutExpired:raise RuntimeError('Pairing watcher did not stop; retain evidence')
        self.tmp.cleanup()
