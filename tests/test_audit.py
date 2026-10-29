import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from face_claim_audit.audit import audit, claims, evidence
from face_claim_audit.phrases import FACE, NOFACE
from tests.cases import GOOD, BAD, NOCLAIM

ROOT = Path(__file__).resolve().parents[1]

class AuditTests(unittest.TestCase):
    def project(self, doc='detects faces', code=None, filename='app.py'):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root/'README.md').write_text(doc)
        if code is not None:
            p = root/filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(code)
        return root

    def check_result(self, result, severity=None, rule='documented-face-claim-false', verdict=None):
        self.assertEqual(result['verdict'], verdict or ('FAIL' if severity == 'HIGH' else 'PASS'))
        self.assertEqual(len(result['findings']), 1 if severity else 0)
        if severity:
            self.assertEqual(result['findings'][0]['severity'], severity)
            self.assertEqual(result['findings'][0]['rule'], rule)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'face_claim_audit', *map(str,args)], capture_output=True, text=True)

    def test_testonly(self):
        for filename in ['tests/check.py', 'test_impl.py', 'impl_test.py']:
            with self.subTest(filename=filename):
                root = self.project(code=GOOD[0], filename=filename)
                self.check_result(audit(root), 'MEDIUM')
                self.check_result(audit(root, fail_on='MEDIUM'), 'MEDIUM', verdict='FAIL')
                self.assertEqual(self.cli(root).returncode, 0)
                self.assertEqual(self.cli(root,'--fail-on','MEDIUM').returncode, 2)

    def test_no_source(self):
        self.check_result(audit(self.project()), 'HIGH')
        self.check_result(audit(self.project('no face recognition')))

    def test_fences_inline_paragraphs(self):
        for doc in ['```text\ndetects faces\n```', '~~~\ndetects faces\n~~~']:
            self.check_result(audit(self.project(doc)))
        for doc in ['`detects faces`', 'DETECTS-\nFACES', 'detects\nfaces']:
            self.check_result(audit(self.project(doc)), 'HIGH')
        self.assertEqual(claims('detects\n\nfaces'), (False,False))
        self.assertEqual(claims("doesn't detect faces"), (False,True))
        self.assertEqual(claims('predetects faces'), (False,False))

    def test_docs_scope_ignore(self):
        root=self.project('neutral')
        (root/'docs').mkdir()
        (root/'docs/nested.md').write_text('detects faces')
        self.check_result(audit(root), 'HIGH')
        self.check_result(audit(root, ['docs/*']))
        self.assertEqual(self.cli(root,'--ignore','docs/*').returncode, 0)
        (root/'docs/nested.md').unlink()
        (root/'OTHER.md').write_text('detects faces')
        self.check_result(audit(root))

    def test_excluded_sources(self):
        for name in ['docs/a.py','examples/a.py','fixtures/a.py']:
            self.check_result(audit(self.project(code=GOOD[0],filename=name)), 'HIGH')
        root=self.project()
        outside=self.project(code=GOOD[0])
        (root/'link.py').symlink_to(outside/'app.py')
        (root/'linked').symlink_to(outside, target_is_directory=True)
        self.check_result(audit(root), 'HIGH')

    def test_env_never_read(self):
        root=self.project('neutral')
        (root/'.env').write_text('MARKER_ONLY')
        original=Path.read_text
        def guarded(path,*args,**kwargs):
            self.assertNotEqual(path.name,'.env')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',guarded):
            self.check_result(audit(root))

    def test_self_audit(self):
        self.assertEqual(claims((ROOT/'README.md').read_text()), (False,False))
        self.check_result(audit(ROOT))

    def test_cli(self):
        self.assertEqual(self.cli('--version').stdout.strip(),'0.1.0')
        self.assertEqual(self.cli('/nonexistent/face-audit-path').returncode,1)
        root=self.project(code='pass')
        run=self.cli(root,'--json','--verbose')
        self.assertEqual(run.returncode,2)
        self.check_result(json.loads(run.stdout),'HIGH')
        self.assertIn('Scanned',self.cli(root,'--verbose').stdout)

    def test_packaging(self):
        for name in ['LICENSE','README.md','MANIFEST.in','pyproject.toml']:
            self.assertTrue((ROOT/name).is_file())
        metadata=(ROOT/'pyproject.toml').read_text()
        self.assertIn('face-claim-audit = "face_claim_audit.audit:main"',metadata)
        self.assertIn('recursive-include tests', (ROOT/'MANIFEST.in').read_text())
        self.assertIn('MIT License',(ROOT/'LICENSE').read_text())
        for path in list((ROOT/'face_claim_audit').glob('*.py'))+[ROOT/'README.md']:
            text=path.read_text()
            self.assertIsNone(re.search(r'\bpython\s+(?:-m|[^\s]+\.py)',text))
            for secret in ['AKIA'+'0123456789ABCDEF', '-----BEGIN '+'PRIVATE KEY-----']:
                self.assertNotIn(secret,text)

    def test_max_two(self):
        self.check_result(audit(self.project('detects faces. no face recognition',GOOD[0])), 'HIGH','documented-no-face-claim-false')

    def test_imported_dotted_face_detection_provider(self):
        code = 'from vendor.face_detection import FaceDetection as FD\nFD()'
        self.check_result(audit(self.project(code=code)))

    def test_syntax_error(self):
        self.assertFalse(evidence('def !'))


def add_case(name, fn):
    setattr(AuditTests, name, fn)

for i, code in enumerate(GOOD):
    def test(self, code=code):
        self.check_result(audit(self.project(code=code)))
    add_case('test_good_%02d'%i,test)
for i, code in enumerate(BAD):
    def test(self, code=code):
        self.check_result(audit(self.project(code=code)), 'HIGH')
    add_case('test_bad_%02d'%i,test)
for i, phrase in enumerate(FACE):
    def test(self, phrase=phrase):
        self.assertEqual(claims(phrase),(True,False))
        self.check_result(audit(self.project(phrase)), 'HIGH')
    add_case('test_face_phrase_%02d'%i,test)
for i, phrase in enumerate(NOFACE):
    def test(self, phrase=phrase):
        self.assertEqual(claims(phrase),(False,True))
        self.check_result(audit(self.project(phrase)))
        root=self.project(phrase,GOOD[0])
        self.check_result(audit(root),'HIGH','documented-no-face-claim-false')
        self.assertEqual(self.cli(root).returncode,2)
    add_case('test_negative_phrase_%02d'%i,test)
for i, phrase in enumerate(NOCLAIM):
    def test(self, phrase=phrase):
        self.check_result(audit(self.project(phrase)))
        self.check_result(audit(self.project(phrase,GOOD[0])))
    add_case('test_no_claim_%02d'%i,test)
