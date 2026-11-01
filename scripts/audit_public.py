#!/usr/bin/env python3
"""Audit the actual public candidate set, not ignored build/cache artifacts."""
import ast
import json
from pathlib import Path
import re
import subprocess
from common import ROOT


def candidates():
    top = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--show-toplevel'], text=True).strip()
    if Path(top).resolve() != ROOT:
        raise RuntimeError('Initialize a separate Git repository here before auditing; never audit the parent workspace repository')
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'])
    return sorted(set(raw.decode().split('\0')) - {''})


def main():
    files = candidates(); issues = []; total = 0
    forbidden_parts = {'.cache', 'core', 'runtime', 'runs', 'evidence', 'downloads', 'build', 'apps', '__pycache__'}
    forbidden_suffixes = {'.pem','.key','.pk8','.p12','.jks','.keystore','.pub','.crt','.cer','.der','.db','.sqlite','.apk','.apks','.idsig','.jar','.zip','.gz','.pcm','.wav','.mp4','.qcow2','.img'}
    patterns = [r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
        r'\bgh[pousr]_[A-Za-z0-9]{20,}\b', r'\bgithub_pat_[A-Za-z0-9_]{20,}\b',
        r'\bAKIA[0-9A-Z]{16}\b', r'\bAIza[0-9A-Za-z_-]{30,}\b', r'\bsk-proj-[0-9A-Za-z_-]{20,}\b',
        r'/User[s]/[^/\s]+/', r'/Volume[s]/[^/\s]+/', r'\b0000[0-9A-F]{16}\b']
    allowed_macs = {'AA:BB:CC:DD:EE:FF','AA:BB:CC:DD:EE:01','00:11:22:33:44:55'}
    for name in files:
        p = ROOT / name
        if p.is_symlink(): issues.append(name + ': symlink not allowed'); continue
        if not p.is_file(): issues.append(name + ': missing file'); continue
        if forbidden_parts.intersection(Path(name).parts) or p.suffix.lower() in forbidden_suffixes:
            issues.append(name + ': generated/private/binary artifact'); continue
        data = p.read_bytes(); total += len(data)
        indexed = subprocess.run(['git','-C',str(ROOT),'show',':' + name], capture_output=True)
        if indexed.returncode == 0 and indexed.stdout != data:
            issues.append(name + ': index differs from working tree; stage reviewed changes then audit again')
        if len(data) > 2 * 1024 * 1024 or b'\0' in data:
            issues.append(name + ': unexpected binary or oversized file'); continue
        text = data.decode('utf-8')
        for pattern in patterns:
            if re.search(pattern, text): issues.append(name + ': private credential/workstation pattern')
        for address in re.findall(r'(?i)\b(?:[a-f0-9]{2}[:-]){5}[a-f0-9]{2}\b', text):
            if address.upper().replace('-', ':') not in allowed_macs:
                issues.append(name + ': non-example network identifier')
        if p.suffix == '.py':
            try: ast.parse(text, filename=name)
            except SyntaxError: issues.append(name + ': Python syntax error')
        if p.suffix == '.md':
            for link in re.findall(r'\]\(([^\s)]+)\)', text):
                target = link.split('#', 1)[0]
                if target and not re.match(r'[a-zA-Z]+://', target) and not (p.parent / target).exists():
                    issues.append(name + ': broken local link: ' + target)
    required = ['README.md','AGENTS.md','NOTICE.md','LICENSE','dependencies.lock.json',
        'docs/SETUP.md','docs/ARCHITECTURE.md','docs/RECOVERY.md','docs/VALIDATION.md','docs/AGENT_RUNBOOK.md']
    for name in required:
        if name not in files: issues.append('Missing public document: ' + name)
    # The assertion string is assembled to avoid matching this script's own private-key rule.
    ignored_examples = ['.cache/signing/test' + '.pem','bridge/wireless-session/runtime/wifi-recovery.json',
        'bridge/emulator-lab/evidence/capture' + '.pcm','bridge/core/build/output']
    checked = subprocess.run(['git','-C',str(ROOT),'check-ignore','--stdin'],
        input='\n'.join(ignored_examples)+'\n', text=True, capture_output=True)
    if set(checked.stdout.splitlines()) != set(ignored_examples): issues.append('Ignore policy does not cover private generated examples')
    print(json.dumps({'files_checked':len(files),'source_bytes':total,'issues':issues,
        'ignored_private_artifacts_checked':len(ignored_examples)}, indent=2))
    if issues: raise SystemExit(1)


if __name__ == '__main__': main()
