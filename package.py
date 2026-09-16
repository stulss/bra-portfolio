"""Package only an explicit allowlist; never archive the original private projects."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from build import ROOT, build


def package() -> Path:
    build(ROOT / 'input', ROOT / 'preview')
    files = ['README.md', 'build.py', 'notion_sync.py', 'test_build.py', 'package.py', 'template.html', 'style.css']
    files += [f'input/{name}' for name in ('profile.json', 'ritual.json', 'attendance.json', 'tasks.json', 'paper.md')]
    files += [f'preview/{name}' for name in ('index.html', 'style.css', 'documents.html', 'paper.html', 'metrics.json', 'candidates.json')]
    dest = ROOT / 'submission' / 'device.zip'
    dest.parent.mkdir(exist_ok=True)
    with ZipFile(dest, 'w') as archive:
        for name in sorted(files):
            info = ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, (ROOT / name).read_bytes())
    return dest


if __name__ == '__main__':
    print(package())
