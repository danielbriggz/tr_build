"""
Run this before compiling the NSIS installer.
Computes CRC32 hashes of bundled binaries and stamps them into transcrire.nsi.

Usage:
    python stamp_hashes.py
"""
import binascii, pathlib, re

FILES = {
    "PYTHON_CRC_PLACEHOLDER": "files/python-3.12.0-amd64.exe",
    "FFMPEG_CRC_PLACEHOLDER":  "files/ffmpeg.exe",
}

nsi_path = pathlib.Path("transcrire.nsi")
nsi = nsi_path.read_text(encoding="utf-8")

for placeholder, filepath in FILES.items():
    p = pathlib.Path(filepath)
    if not p.exists():
        print(f"[skip] {filepath} not found — placeholder left as-is.")
        continue
    crc = format(binascii.crc32(p.read_bytes()) & 0xFFFFFFFF, "08X")
    nsi = nsi.replace(placeholder, crc)
    print(f"[ok]   {filepath} → CRC32 {crc}")

nsi_path.write_text(nsi, encoding="utf-8")
print("\nHashes stamped into transcrire.nsi.")
