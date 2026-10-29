"""Offline documentation and AST checks; audited code is never executed."""
import argparse
import ast
import fnmatch
import json
import os
import re
from pathlib import Path

from . import __version__
from .phrases import FACE, NOFACE


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' '))


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            lines.append('')
        elif fence is None:
            lines.append(line)
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        paragraph = normalize(paragraph)
        for phrase in sorted(NOFACE, key=len, reverse=True):
            paragraph, count = re.subn(r'\b' + re.escape(phrase) + r'\b', ' ', paragraph)
            negative |= bool(count)
        positive |= any(re.search(r'\b' + re.escape(p) + r'\b', paragraph) for p in FACE)
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    aliases = {}
    shadows = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for item in node.names:
                aliases[item.asname or item.name] = node.module + '.' + item.name

    def resolve(node):
        if isinstance(node, ast.Name):
            return '' if node.id in shadows else aliases.get(node.id, '')
        if isinstance(node, ast.Attribute):
            base = resolve(node.value)
            return base + '.' + node.attr if base else ''
        return ''

    def construction(node):
        if not isinstance(node, ast.Call):
            return None
        path = resolve(node.func)
        if path == 'cv2.CascadeClassifier' and any(isinstance(a, ast.Constant) and isinstance(a.value, str) and 'face' in a.value.lower() for a in node.args):
            return 'cascade'
        if path.endswith('.face_detection.FaceDetection'):
            return 'media'
        return None

    def key(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = key(node.value)
            return base + '.' + node.attr if base else None
        return None

    bound = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            kind = construction(node.value)
            if kind:
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    bound[key(target)] = kind
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                kind = construction(item.context_expr)
                if kind and item.optional_vars:
                    bound[key(item.optional_vars)] = kind
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        path = resolve(node.func)
        if path in {'face_recognition.' + name for name in ('face_locations', 'face_encodings', 'compare_faces', 'face_distance')} or path == 'dlib.get_frontal_face_detector':
            return True
        if construction(node) == 'media':
            return True
        if isinstance(node.func, ast.Attribute):
            kind = construction(node.func.value) or bound.get(key(node.func.value))
            if (node.func.attr, kind) in {('detectMultiScale', 'cascade'), ('process', 'media')}:
                return True
    return False


def audit(root, ignore=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir() or not os.access(root, os.R_OK | os.X_OK):
        raise ValueError('Root must be a readable directory')
    pos = neg = prod = test = False
    scanned = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not Path(directory, d).is_symlink())
        for name in sorted(files):
            path = Path(directory, name)
            rel = path.relative_to(root)
            if path.is_symlink() or any(fnmatch.fnmatch(rel.as_posix(), g) for g in ignore):
                continue
            parts = rel.parts[:-1]
            is_doc = rel.as_posix() == 'README.md' or ('docs' in parts and path.suffix.lower() == '.md')
            if not is_doc and path.suffix != '.py':
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeError) as exc:
                raise ValueError('Cannot read ' + rel.as_posix()) from exc
            scanned += 1
            if is_doc:
                p, n = claims(text)
                pos |= p
                neg |= n
            elif not any(p in {'fixtures', 'docs', 'examples'} for p in parts):
                found = evidence(text)
                if 'tests' in parts or name.startswith('test_') or name.endswith('_test.py'):
                    test |= found
                else:
                    prod |= found
    findings = []
    if pos and not prod:
        findings.append({'rule': 'documented-face-claim-false', 'severity': 'MEDIUM' if test else 'HIGH', 'message': 'Documented picture-face capability lacks production evidence.'})
    if neg and prod:
        findings.append({'rule': 'documented-no-face-claim-false', 'severity': 'HIGH', 'message': 'Documented absence conflicts with production evidence.'})
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return {'verdict': 'FAIL' if failed else 'PASS', 'findings': findings, 'files_scanned': scanned}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check documented picture-face claims against Python source.')
    parser.add_argument('root', nargs='?', default='.')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', action='append', default=[])
    parser.add_argument('--fail-on', choices=('HIGH', 'MEDIUM'), default='HIGH')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.ignore, args.fail_on)
    except (ValueError, OSError) as exc:
        if args.json:
            print(json.dumps({'error': str(exc)}))
        else:
            print(str(exc))
        return 1
    if args.json:
        print(json.dumps(result))
    else:
        print(result['verdict'])
        for finding in result['findings']:
            print('{severity} {rule}: {message}'.format(**finding))
        if args.verbose:
            print('Scanned {} files'.format(result['files_scanned']))
    return 2 if result['verdict'] == 'FAIL' else 0
