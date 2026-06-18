"""
Run this before compiling the NSIS installer.
Computes MD5 hashes of bundled binaries and stamps them into transcrire.nsi.

Usage:
    python stamp_hashes.py
"""
import hashlib
import pathlib
import re

# Map: filename (as it appears in the !insertmacro CheckFileHash call) -> local path
FILES = {
    "ffmpeg.exe": "files/ffmpeg.exe",
}

nsi_path = pathlib.Path("transcrire.nsi")
nsi = nsi_path.read_text(encoding="utf-8")

for filename, filepath in FILES.items():
    p = pathlib.Path(filepath)
    if not p.exists():
        print(f"[skip] {filepath} not found.")
        continue

    md5 = hashlib.md5(p.read_bytes()).hexdigest()

    pattern = re.compile(
        r'(!insertmacro CheckFileHash "\$EXEDIR\\files\\' + re.escape(filename) + r'"\s+")[0-9a-fA-F]{32}(")'
    )

    new_nsi, count = pattern.subn(rf"\g<1>{md5}\g<2>", nsi)
    if count == 0:
        print(f"[warn] No CheckFileHash line found for {filename} — hash not stamped.")
        continue

    nsi = new_nsi
    print(f"[ok]   {filepath} -> MD5 {md5}")

nsi_path.write_text(nsi, encoding="utf-8")
print("\nHashes stamped into transcrire.nsi.")
