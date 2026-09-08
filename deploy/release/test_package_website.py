import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from package_website import FILES, package

class ReleaseTests(unittest.TestCase):
    def test_only_allowlisted_assets_and_no_connected_patient_flow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in FILES:
                (root / name).write_text('{}' if name.endswith('.json') else 'asset')
            (root / 'care-services.json').write_text('{"live_care_enabled":false}')
            (root / 'care-access.html').write_text('<body data-service-mode="connected">')
            (root / '.env').write_text('must never ship')
            output = root / 'release.zip'
            package(root, output)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), set(FILES) | {'release-manifest.json'})
                self.assertIn(b'data-service-mode="walkthrough"', archive.read('care-access.html'))
            (root / 'care-services.json').write_text('{"live_care_enabled":true}')
            with self.assertRaises(ValueError):
                package(root, root / 'unsafe.zip')
            self.assertFalse((root / 'unsafe.zip').exists())
            (root / 'care-services.json').write_text('{"live_care_enabled":false}')
            (root / 'care-access.html').write_text('<body>')
            with self.assertRaises(ValueError):
                package(root, root / 'unknown.zip')
