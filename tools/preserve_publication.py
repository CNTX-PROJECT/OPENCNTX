"""Read-only backup before owner-authorized publication maintenance."""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import zipfile

REPO = 'CNTX-PROJECT/OPENCNTX'
API = 'https://api.github.com/repos/' + REPO
ROOT = Path(os.environ['RUNNER_TEMP']) / 'opencntx-preserved'
ROOT.mkdir()
DATA = ROOT / 'backup'
DATA.mkdir()

def api(path):
    req = urllib.request.Request(API + path, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'opencntx-publication-maintenance',
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)

def pages(path):
    result = []
    for page in range(1, 21):
        part = api(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
        result.extend(part)
        if len(part) < 100:
            return result
    raise RuntimeError('Pagination exceeded the safety bound')

releases = pages('/releases')
tags = pages('/tags')
branches = pages('/branches')
for name, value in [('releases', releases), ('tags', tags), ('branches', branches), ('repository', api('')), ('open-prs', pages('/pulls?state=open')), ('rules', api('/rulesets/20518984'))]:
    (DATA / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
subprocess.run(['git','bundle','create',str(DATA / 'repository.bundle'),'--all'], check=True)
subprocess.run(['git','bundle','verify',str(DATA / 'repository.bundle')], check=True)
for name, ref in [('main', '6fc196b5ec90370c93c204a115ac58c73fd2bb32'), ('release-185', '734ad894e20a34013f155ba8e7d3172cedd24c2e'), ('baseline-176', 'v1.7.6')]:
    subprocess.run(['git','archive','--format=tar','--output',str(DATA / (name + '.tar')),ref], check=True)

def download(job):
    tag, asset = job
    name = asset['name']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', tag) or Path(name).name != name:
        raise RuntimeError('Nonportable backup path')
    url = asset['browser_download_url']
    if not url.startswith('https://github.com/' + REPO + '/releases/download/'):
        raise RuntimeError('Unexpected asset host')
    path = DATA / 'releases' / tag / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=45) as response:
        content = response.read(25_000_001)
    sha = hashlib.sha256(content).hexdigest()
    if len(content) > 25_000_000 or len(content) != asset['size']:
        raise RuntimeError('Unexpected asset size: ' + name)
    if asset.get('digest') and asset['digest'] != 'sha256:' + sha:
        raise RuntimeError('Asset digest differs: ' + name)
    path.write_bytes(content)
    return {'tag':tag,'asset_id':asset['id'],'path':path.relative_to(DATA).as_posix(),'bytes':len(content),'sha256':sha}

jobs = [(release['tag_name'], asset) for release in releases for asset in release['assets']]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    manifest = list(executor.map(download, jobs))
(DATA / 'asset-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
checksums = []
for path in sorted(DATA.rglob('*')):
    if path.is_file():
        checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.relative_to(DATA).as_posix())
(DATA / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
archive = ROOT / 'OPENCNTX_before_cleanup.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
    for path in sorted(DATA.rglob('*')):
        if path.is_file():
            output.write(path, path.relative_to(DATA))
import shutil
shutil.rmtree(DATA)
summary = {'status':'PRESERVED_NO_DELETIONS','releases':len(releases),'tags':len(tags),'assets':len(manifest),'backup_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'backup_bytes':archive.stat().st_size}
(ROOT / 'preservation.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary, indent=2))
