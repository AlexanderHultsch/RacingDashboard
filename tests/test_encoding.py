"""Every text file is plain UTF-8: no byte-order mark and no characters broken by a wrong conversion (UTF-8 read
as Windows-1252 and written again turns "°" into "Â°" and "–" into "â€“"; it happened once with a PowerShell
edit of ui/js/rd.js and showed "80Â°" on the tyre tiles)."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".py", ".js", ".css", ".html", ".md", ".toml", ".bat", ".ps1", ".txt", ".json"}
BROKEN = ("Â°", "Â·", "â€", "Ã¤", "Ã¶", "Ã¼", "�")


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
