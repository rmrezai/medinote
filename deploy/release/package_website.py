"""Build an allowlisted, preview-only website release without AWS credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FILES = ('index.html', 'tree-health.css', 'tree-health.js', 'care-services.json',
         'care-access.html', 'care-access.js', 'care-access-model.js',
         'transitional-care.html', 'hospital-medicine.html')

def package(source, output):
    assets = {name: (source / name).read_bytes() for name in FILES}
    catalog = json.loads(assets['care-services.json'])
    if catalog.get('live_care_enabled') is not False:
        raise ValueError('Release requires live care disabled')
    page = assets['care-access.html'].decode()
    marker = 'data-service-mode="connected"'
    preview = 'data-service-mode="walkthrough"'
    if page.count(marker) + page.count(preview) != 1:
        raise ValueError('Unknown patient access mode')
    assets['care-access.html'] = page.replace(marker, preview).encode()
    manifest = {'format': 1, 'mode': 'website-walkthrough',
                'creates_accounts': False, 'accepts_clinical_intake': False,
                'books_appointments': False, 'accepts_payments': False,
                'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in assets.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in assets.items():
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        archive.writestr(zipfile.ZipInfo('release-manifest.json', (2026, 1, 1, 0, 0, 0)), json.dumps(manifest, indent=2, sort_keys=True))
    return manifest

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('clinistry/website'))
    parser.add_argument('--output', type=Path, default=Path('release/clinistry-website.zip'))
    args = parser.parse_args()
    package(args.source, args.output)
    print('Website walkthrough release prepared; no AWS changes made.')
