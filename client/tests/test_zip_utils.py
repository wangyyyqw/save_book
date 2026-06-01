import io
import zipfile
from pathlib import Path
import unittest

from qidian_save.zip_utils import UnsafeZipPathError, safe_extract_zip


class SafeExtractZipTests(unittest.TestCase):
    def _zip_bytes(self, entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in entries.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_extracts_normal_relative_files(self):
        data = self._zip_bytes({"book/1.txt": "hello"})
        out = Path(self._tmp.name) / "out"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            extracted = safe_extract_zip(zf, out)
        self.assertEqual((out / "book" / "1.txt").read_text(encoding="utf-8"), "hello")
        self.assertEqual(extracted, [out / "book" / "1.txt"])

    def test_rejects_parent_directory_escape(self):
        data = self._zip_bytes({"../escape.txt": "bad"})
        out = Path(self._tmp.name) / "out"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with self.assertRaises(UnsafeZipPathError):
                safe_extract_zip(zf, out)

    def test_rejects_absolute_path(self):
        data = self._zip_bytes({"/absolute.txt": "bad"})
        out = Path(self._tmp.name) / "out"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            with self.assertRaises(UnsafeZipPathError):
                safe_extract_zip(zf, out)

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
