"""Every text file is plain UTF-8: no byte-order mark and no characters broken by a wrong conversion (UTF-8 read
as Windows-1252 and written again turns the degree sign into "A-circumflex + degree" and a dash into three
characters; it happened once with a PowerShell edit of ui/js/rd.js and showed a stray A-circumflex after the
tyre temperatures). The broken forms are built from character codes below, so this file does not match itself."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".py", ".js", ".css", ".html", ".md", ".toml", ".bat", ".ps1", ".txt", ".json"}
# the broken forms, built from character codes: A-circumflex + degree / middle dot, a-circumflex + euro sign
# (start of a broken dash or ellipsis), A-tilde + the second byte of a, o, u with umlaut, the replacement
# character
BROKEN = tuple("".join(map(chr, codes)) for codes in
               ((0xC2, 0xB0), (0xC2, 0xB7), (0xE2, 0x20AC), (0xC3, 0xA4), (0xC3, 0xB6), (0xC3, 0xBC), (0xFFFD,)))


def text_files():
    try:
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        names = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [ROOT / n for n in names if Path(n).suffix.lower() in TEXT and (ROOT / n).is_file()]


class Encoding(unittest.TestCase):
    def test_utf8_without_bom_or_broken_characters(self):
        for path in text_files():
            data = path.read_bytes()
            name = path.relative_to(ROOT)
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"), f"{name}: byte-order mark")
            text = data.decode("utf-8")                                  # fails on bytes that are not UTF-8
            for mark in BROKEN:
                self.assertNotIn(mark, text, f"{name}: broken character {mark!r}")


if __name__ == "__main__":
    unittest.main()
