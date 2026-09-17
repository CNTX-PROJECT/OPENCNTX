"""Prepare the approved repository cleanup; never change an installed runtime."""
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT=Path.cwd()
BRANCH='maintenance/github-cleanup-20260918'
RELEASE='734ad894e20a34013f155ba8e7d3172cedd24c2e'
BASELINE='6fc196b5ec90370c93c204a115ac58c73fd2bb32'
TMP=Path(os.environ['RUNNER_TEMP'])

def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def text(path):
    return (ROOT/path).read_text(encoding='utf-8')

def write(path,value):
    target=ROOT/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(value,encoding='utf-8')

def replace(path,old,new,required=True):
    value=text(path)
    if required and old not in value:
        raise RuntimeError(f'Missing expected input in {path}: {old[:100]}')
    write(path,value.replace(old,new))

if subprocess.check_output(['git','branch','--show-current'],text=True).strip()!=BRANCH:
    raise RuntimeError('Wrong maintenance branch')
if subprocess.check_output(['git','rev-parse','origin/main'],text=True).strip()!=BASELINE:
    raise RuntimeError('Main changed since the reviewed baseline')
# Retain actual old bytes locally so deleting old download listings cannot break CI.
backup=TMP/'preserved-download'
backup.mkdir()
command(['gh','release','download','archive-20260918','--dir',str(backup)])
archive=backup/'OPENCNTX_before_cleanup.zip'
if hashlib.sha256(archive.read_bytes()).hexdigest()!='3a4e71dc4e4d9eee562aa128e52e5888cf25c85665d6d7ea744fdab10bdf2c6e':
    raise RuntimeError('The preserved archive changed')
fixtures=ROOT/'tests/fixtures/release-baselines'
fixtures.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(archive) as bundle:
    old=bundle.read('releases/v0.3.0/opencntx-0.3.0-py3-none-any.whl')
    releases=json.loads(bundle.read('releases.json'))
    tags=json.loads(bundle.read('tags.json'))
if hashlib.sha256(old).hexdigest()!='6dee59d5255c73278400c05217abb298abb50a51f5998c7fb9d1c41e8e027cc6':
    raise RuntimeError('Old compatibility wheel differs')
(fixtures/'opencntx-0.3.0-py3-none-any.whl').write_bytes(old)
# Rebuild the missing historical baseline without calling it the original artifact.
source=TMP/'source176'
command(['git','worktree','add','--detach',str(source),'v1.7.6'])
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
tree=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip()
with (TMP/'rebuild176.log').open('w') as log:
    command([sys.executable,'tools/release_artifacts.py','build','--repository','.', '--output','dist','--expected-commit',commit,'--expected-tree',tree],cwd=source,stdout=log,stderr=subprocess.STDOUT)
wheel=source/'dist/opencntx-1.7.6-py3-none-any.whl'
shutil.copyfile(wheel,fixtures/wheel.name)
new_hash=hashlib.sha256(wheel.read_bytes()).hexdigest()
manifest={'format':'opencntx-maintenance-baselines-v1','baselines':[
 {'version':'0.3.0','file':'opencntx-0.3.0-py3-none-any.whl','kind':'ORIGINAL_PUBLISHED_BYTES','sha256':hashlib.sha256(old).hexdigest()},
 {'version':'1.7.6','file':wheel.name,'kind':'SOURCE_REBUILT_NOT_ORIGINAL','sha256':new_hash,'source_commit':commit,'source_tree':tree,'original_missing_wheel_sha256':'b27d08f9851b9a8f1a30cb7fc71c3e94eedb579141cdce3609424b753071785f','python':sys.version.split()[0]}
]}
write('tests/fixtures/release-baselines/manifest.json',json.dumps(manifest,indent=2)+'\n')
write('docs/release-baselines.md',f'''# Release baselines

[Documentation](README.md) · [Release status](releases.md) · [History](history.md)

Publication listings and compatibility evidence are different resources. Removing an obsolete download must not remove the bytes used by a test.

## Original historical input

The original 0.3.0 wheel is retained as a test fixture with SHA-256 `6dee59d5255c73278400c05217abb298abb50a51f5998c7fb9d1c41e8e027cc6`. The R8 upgrade test reads these local bytes and still verifies the original hash. It no longer depends on a public pre-1.7.0 release URL.

## Rebuilt 1.7.6 input

The original 1.7.6 release download was absent before this cleanup. Its tag and source remain available. The original expected wheel hash is `b27d08f9851b9a8f1a30cb7fc71c3e94eedb579141cdce3609424b753071785f`.

A new test fixture was built from exact source `{commit}` with the repository's pinned build toolchain. Its SHA-256 is `{new_hash}`. This is **SOURCE_REBUILT_NOT_ORIGINAL**: it is not a restored official artifact or a recommended rollback replacement for an existing installation.

The managed transition tests retain this source-version coverage with the new fixture's explicit identity. Current 1.8.4 upgrade tests use the unchanged original published wheel. Other retained 1.8.x baselines keep their published checksums.

## Manifest and safety

[Fixture manifest](../tests/fixtures/release-baselines/manifest.json) records the exact provenance and hashes. Fixtures are test inputs, not automatic user-installation targets. Historical writer tests retain their exact Git commit identities and the original data-format fixtures remain unchanged.
''')
# Use local exact bytes for the historic R8 check, preserving its hash gate.
replace('tools/r8_hardening.py','import urllib.request\n','')
replace('tools/r8_hardening.py','V030_WHEEL_URL = (\n    "https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/"\n    "v0.3.0/opencntx-0.3.0-py3-none-any.whl"\n)', 'V030_WHEEL_PATH = ROOT / "tests/fixtures/release-baselines/opencntx-0.3.0-py3-none-any.whl"')
replace('tools/r8_hardening.py','        with urllib.request.urlopen(V030_WHEEL_URL, timeout=60) as response:\n            official.write_bytes(response.read())','        official.write_bytes(V030_WHEEL_PATH.read_bytes())')
# Shorten the primary changelog but preserve the older record separately.
changelog=text('CHANGELOG.md')
match=re.search(r'(?m)^## 1\.6\.3 - ',changelog)
if not match:
    raise RuntimeError('Historical changelog split point missing')
early=changelog[match.start():]
early=re.sub(r'\]\((docs/[^)]+)\)',r'](../../\1)',early)
write('docs/history/pre-1.7.0.md','# Pre-1.7.0 history\n\n[History index](../history.md) · [Current release](../releases.md)\n\nHistorical record only. Versions and qualification statements below describe their original dates.\n\n'+early)
recent=changelog[:match.start()]
entry='''## 1.8.5 - 2026-09-17

Regular release: optional compact JSON output through `preview-search --compact`, retaining the existing engine and managed installer. [Release scope](docs/release-1.8.5.md) and [current status](docs/releases.md) describe the original artifact's limited qualification. The live source workflow is `CI_ACTIVE`; source checks do not retroactively change an immutable build record.

Publication maintenance aligns current guides, separates historical navigation, retains local compatibility inputs and checks links and runtime identity. It does not replace published artifacts or implement all proposed product optimizations.

'''
recent=recent.replace('# Changelog\n','# Changelog\n\n'+entry,1)
recent+='\n## Earlier history\n\nPre-1.7.0 records are in the [historical changelog](docs/history/pre-1.7.0.md).\n'
write('CHANGELOG.md',recent)
# Update current instructions, not versioned historical release evidence.
for path in ['docs/start-here.md','docs/faq.md','docs/commands.md','docs/continuity.md','docs/release-artifacts.md','site/index.html']:
    replace(path,'1.8.4','1.8.5')
for path in ['docs/start-here.md','docs/faq.md','docs/continuity.md','docs/release-artifacts.md']:
    original=text(path)
    first,rest=original.split('\n',1)
    note='\n\n> Current download: **v1.8.5**. The original release evidence is limited to the [documented artifact checks](releases.md); retained Stable contracts are not a claim of full new platform or live-host qualification.\n'
    write(path,first+note+'\n'+rest)
# Separate the standard artifact verifier from the legacy scope-limited build record.
replace('docs/release-artifacts.md','## Current public distribution','## Current public distribution\n\nThe published 1.8.5 BUILD-RECORD uses the limited publication builder described in its release notes. The standard reproducible builder and verification commands below describe new local candidates; they do not certify or rewrite those already published files. For the published bytes, compare the exact values in [publication.json](publication.json) and SHA256SUMS. Do not treat a standard-format verification failure on that distinct record as permission to overwrite the release.',False)
# Remove irrelevant historical download guidance from active FAQ.
replace('docs/faq.md','The historical `v0.2.0` Release has none. ', '',False)
replace('docs/release-artifacts.md','- The historical `v0.2.0` GitHub Release has no wheel, sdist, checksum, or\n  build record.\n','',False)
replace('docs/knowledge-layer.md','# The OPENCNTX 1.8.3 knowledge layer','# Knowledge and search',False)
write('docs/knowledge-layer.md',text('docs/knowledge-layer.md')+'\n## Compact output in 1.8.5\n\n`opencntx preview-search "query" --root . --compact --delivery-report` preserves the existing result while removing formatting whitespace. The ordinary index search is unchanged. See [release status](releases.md) for limits and [commands](commands.md) for syntax.\n')
write('docs/commands.md',text('docs/commands.md')+'\n## Compact search output\n\n```text\nopencntx preview-search "query" --root . --compact --delivery-report\n```\n\nThis 1.8.5 route uses the existing full-text engine. `--compact` changes serialization, not result selection. Without it the route emits pretty JSON. Source-byte, estimated-token and delivery-output limits retain the original engine semantics; this is not a provider-token counter.\n')
replace('docs/goal-bound-workflows.md','# Goal-bound workflows in v1.5.0','# Goal-bound workflows',False)
for path in ['docs/adaptive-ai-workflow.md','docs/owner-flow.md','docs/privacy-storage-lifecycle.md']:
    value=text(path).replace('current v1.6.0','retained').replace('Stable v1.6.0','retained')
    first,rest=value.split('\n',1)
    write(path,first+'\n\n> Contract reference. Earlier version numbers identify when behavior was introduced, not the current download. See [release status](releases.md) for 1.8.5 and its evidence boundaries.\n'+rest)
replace('.github/ISSUE_TEMPLATE/bug_report.yml','v0.2.0','v1.8.5')
# Preserve all historical details, but make their role explicit.
for page in sorted((ROOT/'docs').glob('*.md')):
    if re.match(r'(release-1\.[78]\.[0-4]|release-1\.7\.[56]|roadmap-1\.)',page.name) or page.name=='roadmap-plan.md':
        value=page.read_text()
        note='\n> Historical version record, not the active backlog. [Current release](releases.md) · [Current work](roadmap.md) · [History](history.md).\n'
        if value.startswith('---\n'):
            end=value.find('\n---',4)+4
            value=value[:end]+'\n'+note+value[end:]
        else:
            first,rest=value.split('\n',1)
            value=first+'\n'+note+rest
        page.write_text(value)
# Keep historical diagrams accessible without promoting them to the landing page.
write('docs/history.md',text('docs/history.md')+'\n<details>\n<summary>Historical foundation diagram</summary>\n\n<picture><source media="(prefers-color-scheme: dark)" srcset="../assets/docs/roadmap-dark.svg"><img src="../assets/docs/roadmap.svg" alt="Historical foundation milestones, not the current development plan"></picture>\n\n</details>\n')
# Expose every specialized guide from one second-level reference page.
primary={'README.md','history.md','releases.md','roadmap.md','reference.md','start-here.md','install-and-update.md','repository-maintenance.md','release-baselines.md'}
references=[]
for page in sorted((ROOT/'docs').glob('*.md')):
    if page.name in primary or page.name.startswith(('release-1.','roadmap-')):
        continue
    title=next((line.lstrip('# ').strip() for line in page.read_text().splitlines() if line.startswith('# ')),page.stem)
    references.append(f'- [{title}]({page.name})')
write('docs/reference.md','# Technical reference\n\n[Documentation](README.md) · [Current release](releases.md) · [History](history.md)\n\nLoad the guide relevant to your task. Contract documents and fixture-host specifications keep their own maturity limits; they do not activate native integrations.\n\n'+'\n'.join(references)+'\n\n[Website source](../site/README.md) · [Baseline maintenance](release-baselines.md) · [Repository maintenance](repository-maintenance.md)\n')
for page in (ROOT/'docs').glob('*CONTRACT.md'):
    value=page.read_text()
    value+='\n[Technical reference](reference.md) · [Current release](releases.md)\n'
    page.write_text(value)
# A maintenance gate is distinct from the strict release builder.
replace('tools/release_version_gate.py','    parser.add_argument("--json", action="store_true")','    parser.add_argument("--json", action="store_true")\n    parser.add_argument("--maintenance", action="store_true", help="verify unchanged released runtime with bounded documentation and verification maintenance")')
old='''        result = inspect_release_version(
            arguments.repository,
            expected_version=arguments.expected_version,
        )'''
new='''        if arguments.maintenance:
            from publication_maintenance import inspect_maintenance

            result = inspect_maintenance(arguments.repository)
            if arguments.expected_version is not None and result["project_version"] != arguments.expected_version:
                raise ReleaseVersionError("unexpected maintenance package version")
            inspect_current_version_surfaces(arguments.repository)
        else:
            result = inspect_release_version(
                arguments.repository,
                expected_version=arguments.expected_version,
            )'''
replace('tools/release_version_gate.py',old,new)
policy=text('docs/contracts-and-compatibility.md')
start=policy.index('After a stable release, documentation may be corrected')
end=policy.index('\n\nBackward-compatible continuity',start)
policy=policy[:start]+'''After a release, the strict release-version gate still rejects changed source at the same version. The separately selected `--maintenance` mode permits named documentation and verification maintenance only when all runtime/schema bytes, package metadata, build manifest, dependencies and license are content-identical to the published tag. It reports `RELEASE_RUNTIME_ALIGNED_MAINTENANCE`, not a new release or artifact qualification. This content check supports squash-merged publication repairs without inventing tag ancestry. Unknown paths, runtime changes, unclean checkouts and arbitrary deletions fail closed. The immutable release tag and downloadable files are never replaced by a maintenance commit.'''+policy[end:]
write('docs/contracts-and-compatibility.md',policy)
# Bind all primary public version claims, without requiring a false Stable certification.
entries=[
 ('src/opencntx/__init__.py',['__version__ = "{version}"'],'package'),
 ('README.md',['Download v{version}'],'published'),
 ('docs/README.md',['Current published package: \\*\\*{version}'],'published'),
 ('docs/releases.md',['Published package: v{version}','opencntx-{version}-py3-none-any.whl'],'published'),
 ('docs/roadmap.md',['Current published release: \\*\\*v{version}'],'published'),
 ('docs/install-and-update.md',['Install and update OPENCNTX {version}'],'published'),
 ('site/index.html',['releases/tag/v{version}','opencntx-{version}-py3-none-any.whl'],'published'),
 ('docs/start-here.md',['instructions below target v{version}'],'published'),
 ('docs/faq.md',['Current download: \\*\\*v{version}'],'published'),
 ('docs/release-artifacts.md',['Current download: \\*\\*v{version}'],'published'),
 ('docs/continuity.md',['Current download: \\*\\*v{version}'],'published'),
 ('docs/commands.md',['Install and update OPENCNTX {version}'],'published'),
]
write('tests/fixtures/quality/current-version-surfaces-v1.json',json.dumps({'format':'opencntx-current-version-surfaces','format_version':1,'surfaces':[{'path':p,'patterns':patterns,'purpose':'Current published identity, not historical certification','version_source':source} for p,patterns,source in entries]},indent=2)+'\n')
# Update wording-coupled tests to check the new navigation, retaining all historical assertions.
p='tests/test_public_roadmap.py'
value=text(p)
value=value.replace('overview = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")','overview = (ROOT / "docs/history.md").read_text(encoding="utf-8")')
value=value.replace('f"Published software — v{published} Stable"','f"Published package: v{published}"')
value=value.replace('self.assertIn("release scope", releases)','self.assertIn("release scope", releases.lower())')
value=value.replace('"two long routes of 100 tasks each"','"Two long routes of 100 tasks each"')
write(p,value)
p='tests/test_quality.py'
value=text(p)
value=value.replace('''        self.assertIn(
            "Development Status :: 5 - Production/Stable",
            project["classifiers"],
        )''','''        publication = json.loads((DOCS / "publication.json").read_text(encoding="utf-8"))
        self.assertEqual("regular", publication["release_kind"])
        self.assertEqual(version, publication["version"])
        self.assertEqual("targeted-ubuntu-python312", publication["artifact_qualification"])''')
value=value.replace('self.assertIn(f"v{version} Stable", readme)','self.assertIn(f"Download v{version}", readme)')
value=value.replace('self.assertIn("Stable", public_surface)','self.assertIn("release", public_surface.lower())')
write(p,value)
# CI keeps all historical writer tests and adds the real immediate upgrade baseline.
p='.github/workflows/ci.yml'
value=text(p).replace('dist/opencntx-1.8.4-py3-none-any.whl','dist/opencntx-1.8.5-py3-none-any.whl').replace('--expected-candidate 1.8.4','--expected-candidate 1.8.5')
value=value.replace('python tools/release_version_gate.py --repository .','python tools/release_version_gate.py --repository . --maintenance\n\n      - name: Verify public navigation and baseline fixture hashes\n        run: python tools/publication_links.py')
value=value.replace('          - {os: windows-latest, python-version: "3.12", baseline-version: "1.8.3"}','          - {os: windows-latest, python-version: "3.12", baseline-version: "1.8.3"}\n          - {os: ubuntu-latest, python-version: "3.12", baseline-version: "1.8.4"}\n          - {os: windows-latest, python-version: "3.12", baseline-version: "1.8.4"}')
value=value.replace('              "1.8.3": "ae65a2885250c140c142b9d9a21521a91248c9128f7d9967d7ff44ec92b1005f",','              "1.8.3": "ae65a2885250c140c142b9d9a21521a91248c9128f7d9967d7ff44ec92b1005f",\n              "1.8.4": "b3fe658c5071b17e1835be65cc10df3c025dd03677c1be45c9b8aeb977d011d9",')
old='''          urllib.request.urlretrieve(
              f"https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v{version}/"
              f"opencntx-{version}-py3-none-any.whl",
              baseline,
          )'''
new='''          if version == "1.7.6":
              import json
              fixture_root = pathlib.Path("tests/fixtures/release-baselines")
              manifest = json.loads((fixture_root / "manifest.json").read_text())
              fixture = next(item for item in manifest["baselines"] if item["version"] == version)
              if fixture["kind"] != "SOURCE_REBUILT_NOT_ORIGINAL":
                  raise SystemExit("Missing rebuilt-baseline provenance")
              hashes[version] = fixture["sha256"]
              baseline.write_bytes((fixture_root / fixture["file"]).read_bytes())
              print("BASELINE_KIND=SOURCE_REBUILT_NOT_ORIGINAL", fixture["sha256"])
          else:
              urllib.request.urlretrieve(
                  f"https://github.com/CNTX-PROJECT/OPENCNTX/releases/download/v{version}/"
                  f"opencntx-{version}-py3-none-any.whl",
                  baseline,
              )'''
if old not in value:
    raise RuntimeError('Expected CI baseline acquisition missing')
value=value.replace(old,new)
value=value.replace('Build exact candidate and acquire frozen baseline','Build exact candidate and acquire the explicitly identified baseline')
write(p,value)
# Retire one-shot publication scripts without changing the product.
for path in ['.github/workflows/owner-preview-185.yml','.github/workflows/release-185.yml','tools/build_owner_preview_185.py','tools/build_release_185.py']:
    (ROOT/path).unlink(missing_ok=True)
# Mark the earlier preview note as history, not current public instructions.
p='docs/release-1.8.5-preview.md'
value=text(p)
write(p,'> Historical test-build note. The regular [1.8.5 release](releases.md) supersedes this preview. Statements below describe its original publication, not current status.\n\n'+value)
write('docs/repository-maintenance.md','''# Repository maintenance

[Documentation](README.md) · [Current release](releases.md) · [History](history.md)

## Approved scope

Reconcile the 1.8.5 runtime with the default development line; update public navigation and current installation instructions; separate historical records; preserve compatibility inputs before retiring pre-1.7.0 download listings. The actual merge and validation outcome are recorded in the associated pull request and CI, not inferred from this document.

The original 1.8.5 source/runtime and packaging identity are retained. Published wheels, checksums and tags are not replaced. This maintenance does not implement outstanding product optimizations or modify user installations.

## Preservation

The [before-cleanup backup](https://github.com/CNTX-PROJECT/OPENCNTX/releases/tag/archive-20260918) contains the complete Git bundle, 17 release records, 29 tag records and 60 downloaded assets. Archive SHA-256: `3a4e71dc4e4d9eee562aa128e52e5888cf25c85665d6d7ea744fdab10bdf2c6e`. Remote downloaded bytes were compared before any planned release deletion. The original 1.7.6 wheel was already missing and is not falsely claimed as recovered.

## Lasting controls

The publication record pins the regular release, source commit and exact artifact hashes. Twelve declared current-version surfaces are checked separately from history. Offline Markdown/HTML path and anchor checks cover the public documentation. The maintenance gate requires unchanged runtime, schema, package metadata, dependencies and license, and limits other changes to documentation and named verification paths. Full required CI remains protected by the repository ruleset.

Historical writer tests and stored-data fixtures remain intact. The old 0.3.0 wheel is retained locally with its original hash; the rebuilt 1.7.6 fixture has a distinct disclosed identity. Both are verified before use.

## Closing a publication

A publication is complete only after the intended source changes are merged through required checks, public instructions match the actual release, artifact identities are verified, remaining product work is described truthfully, and the publication's temporary branches and pull requests are resolved. Never check off unimplemented product work to make the page look complete.
''')
write('CONTRIBUTING.md',text('CONTRIBUTING.md')+'\n## Publication maintenance\n\nKeep current instructions aligned with [publication.json](docs/publication.json). Run `python tools/publication_links.py` and the selected publication-maintenance gate alongside full CI. A release is not complete while its landing page describes another version or its integration branch remains unhandled. Preserve immutable artifacts and historical compatibility evidence; see [repository maintenance](docs/repository-maintenance.md).\n')
write('docs/platforms.md',text('docs/platforms.md')+'\n## Original 1.8.5 artifact versus maintenance source\n\nThe original 1.8.5 artifacts were checked on Ubuntu/Python 3.12 within the [limited release scope](releases.md). The live `CI_ACTIVE` matrix evaluates the exact maintenance source commit on each listed platform. Source results do not change the original build record or establish native chat integration.\n')
# Refresh only the manifest that binds changed site bytes; styles and visual assets stay unchanged.
p='assets/design-system/visual-baseline-v1.json'
value=text(p)
previous=subprocess.check_output(['git','show',RELEASE+':site/index.html'])
value=value.replace(hashlib.sha256(previous).hexdigest(),hashlib.sha256((ROOT/'site/index.html').read_bytes()).hexdigest())
write(p,value)
# Avoid storing orchestration, credentials or disposable logs in the product tree.
for path in ['.github/workflows/maintenance-publication.yml','temporary_prepare_publication.py','tools/preserve_publication.py']:
    (ROOT/path).unlink(missing_ok=True)
# Format only verification code; released runtime bytes are left alone.
new_tools=['tools/publication_maintenance.py','tools/publication_links.py','tools/release_version_gate.py','tools/r8_hardening.py','tests/test_publication_links.py','tests/test_publication_maintenance.py','tests/test_quality.py','tests/test_public_roadmap.py']
# Resolve import-order lint without suppressing it.
for p in ['tests/test_publication_links.py','tests/test_publication_maintenance.py']:
    value=text(p)
    value=value.replace('import sys\n','import sys\nimport importlib\n')
    value=re.sub(r'from (publication_\w+) import ([^\n]+)',lambda m:'_module = importlib.import_module('+repr(m[1])+')\n'+'\n'.join(name.strip()+' = _module.'+name.strip() for name in m[2].split(',')) ,value,count=1)
    write(p,value)
command([sys.executable,'-m','ruff','check',*new_tools,'--fix'],check=False) if False else None
subprocess.run([sys.executable,'-m','ruff','check',*new_tools,'--fix'],check=False)
command([sys.executable,'-m','ruff','format',*new_tools])
# Commit to the same bounded branch, leaving normal PR checks to qualify it.
command(['git','config','user.name','OPENCNTX maintenance'])
command(['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'])
command(['git','add','-A'])
command(['git','commit','-m','maintenance: reconcile 1.8.5 publication, simplify navigation and preserve test baselines'])
command(['gh','auth','setup-git'])
command(['git','push','origin','HEAD:refs/heads/'+BRANCH])
print('PREPARED_HEAD',subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),flush=True)
print('BASELINE176_FIXTURE',new_hash,flush=True)
checks=[
 [sys.executable,'tools/release_version_gate.py','--repository','.','--maintenance'],
 [sys.executable,'tools/publication_links.py'],
 [sys.executable,'-W','error::ResourceWarning','-m','unittest','discover','-s','tests'],
 [sys.executable,'tools/quality_gate.py','lint'],
 [sys.executable,'tools/quality_gate.py','types'],
]
failed=[]
for args in checks:
    result=subprocess.run(args,text=True,capture_output=True,timeout=720)
    print('CHECK',args,'EXIT',result.returncode,flush=True)
    print(result.stdout[-10000:],flush=True)
    print(result.stderr[-16000:],flush=True)
    if result.returncode:
        failed.append(args)
print('PREPARATION_CHECKS',json.dumps({'failed':failed,'note':'Normal protected PR CI is still required'}),flush=True)
sys.exit(bool(failed))
