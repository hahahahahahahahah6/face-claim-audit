# face-claim-audit 0.1.0

Offline static audit of documented picture-face claims against Python source.
Audited code is parsed with AST and never executed. Runtime dependencies: none.
Requires Python >=3.9.

## Usage

```sh
python3 -m pip install .
face-claim-audit /path/to/project
python3 -m face_claim_audit /path/to/project --json --verbose
python3 -m face_claim_audit /path/to/project --ignore 'docs/old/*' --fail-on MEDIUM
python3 -m unittest discover
python3 -m build
```

The root README.md and Markdown files with a docs path component supply claims.
Fenced blocks are excluded; inline code counts. Paragraph lines are joined,
case is folded, contractions expanded, hyphens replaced with spaces, and
whitespace collapsed. Exact templates use word boundaries, longest first;
negative spans are removed before positive matching.

Production evidence comes from imported, alias-resolved calls in Python files.
The supported providers are face_recognition, dlib, cv2, and mediapipe.
The first provider supports four operations, dlib its frontal detector factory,
cv2 a literal face-cascade construction paired with a bound scan method,
and mediapipe its specified detector construction or bound process method.
Assignments, self attributes, context targets, and chained calls are supported.
Local definitions shadow imports. Bare imports and strings are insufficient.
Tests, fixtures, docs, examples, and symlinked files are excluded from production.
Test evidence produces a MEDIUM finding; absence of production evidence produces
HIGH. Conflicting negative prose produces HIGH. Each family yields at most one
finding. With no claims, the result is PASS regardless of source.

Rules: `documented-face-claim-false`, `documented-no-face-claim-false`.
Default threshold HIGH reports MEDIUM without failing; --fail-on MEDIUM fails
on either severity. Exits: 0 PASS, 2 FAIL, 1 invalid or unreadable root.
JSON includes verdict, findings (rule, severity, message), and files_scanned.

## Limitations

Only the exact templates below count. A bare face or faces, eyes alone,
age or gender estimation, person or body detection, privacy blurring,
camera capture, and image opening are outside claim scope.
A shell call to a system face finder is not counted: a command name in a
string literal is never evidence. Other face stacks, including phone-camera
SDKs, cloud picture-face APIs, and handwriting-specific engines, are out of
scope; only the Python routes described above are counted. Non-literal cascade
paths (variables, joins, or computed expressions) are not counted.
This is module-local static analysis, not runtime or cross-module proof;
syntax-invalid files provide no evidence. No optional provider is imported.
The scanner never opens .env files.

## Exact templates

```text
recognizes faces in photos
recognize faces in photos
recognises faces in photos
recognise faces in photos
recognizes faces in images
recognize faces in images
recognises faces in images
recognise faces in images
detects faces in photos
detect faces in photos
detects faces in images
detect faces in images
identifies faces in photos
identify faces in photos
identifies faces in images
identify faces in images
detects faces in video
detect faces in video
supports facial recognition
support facial recognition
supports face recognition
support face recognition
facial recognition support
face recognition support
recognizes faces
recognize faces
recognises faces
recognise faces
detects faces
detect faces
identifies faces
identify faces
recognizes a face
recognize a face
recognises a face
recognise a face
detects a face
detect a face
identifies a face
identify a face
face recognition
facial recognition
face detection
face identification
does not support facial recognition
does not support face recognition
does not recognize faces in photos
does not recognise faces in photos
does not recognize faces in images
does not recognise faces in images
does not detect faces in photos
does not detect faces in images
does not identify faces in photos
does not identify faces in images
does not recognize faces
does not recognise faces
does not detect faces
does not identify faces
facial recognition not supported
face recognition not supported
face detection not supported
no facial recognition
without facial recognition
no face recognition
without face recognition
no face detection
without face detection
no face identification
without face identification
```
