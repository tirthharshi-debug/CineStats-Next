import io
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from app.services import file_service


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


class ZipExtractionTests(unittest.TestCase):
    def test_extracts_valid_archive_to_unique_directories(self):
        payload = make_zip([
            ("diary.csv", "Date,Name,Year,Rating,Rewatch\n2024-01-01,Example Film,2000,4,No\n"),
            ("watched.csv", "Date,Name,Year\n2024-01-01,Example Film,2000\n"),
        ])
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root):
                first = file_service.extract_zip(payload)
                second = file_service.extract_zip(payload)
                try:
                    self.assertNotEqual(first, second)
                    self.assertTrue(os.path.isfile(os.path.join(first, "diary.csv")))
                    self.assertTrue(os.path.isfile(os.path.join(second, "watched.csv")))
                finally:
                    shutil.rmtree(first, ignore_errors=True)
                    shutil.rmtree(second, ignore_errors=True)

    def test_rejects_path_traversal_and_cleans_partial_directory(self):
        payload = make_zip([("../escaped.txt", "should not be extracted")])
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root):
                with self.assertRaises(ValueError):
                    file_service.extract_zip(payload)
                self.assertEqual(os.listdir(root), [])
                self.assertFalse(os.path.exists(os.path.join(root, "escaped.txt")))

    def test_rejects_archive_with_too_many_members(self):
        payload = make_zip([("one.csv", "x"), ("two.csv", "y")])
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root), patch.object(file_service, "MAX_ZIP_MEMBERS", 1):
                with self.assertRaisesRegex(ValueError, "too many files"):
                    file_service.extract_zip(payload)
                self.assertEqual(os.listdir(root), [])

    def test_rejects_expanded_archive_over_limit(self):
        payload = make_zip([("diary.csv", "x" * 100)])
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root), patch.object(file_service, "MAX_UNCOMPRESSED_SIZE", 10):
                with self.assertRaisesRegex(ValueError, "expands beyond"):
                    file_service.extract_zip(payload)
                self.assertEqual(os.listdir(root), [])

    def test_rejects_invalid_zip_and_cleans_temporary_directory(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root):
                with self.assertRaises(zipfile.BadZipFile):
                    file_service.extract_zip(b"not a zip file")
                self.assertEqual(os.listdir(root), [])

    def test_accepts_valid_letterboxd_csv_structure(self):
        payload = make_zip([
            ("diary.csv", "Date,Name,Year,Rating,Rewatch\n2024-01-01,Example Film,2000,4,No\n"),
        ])
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root):
                extracted = file_service.extract_zip(payload)
                try:
                    file_service.validate_letterboxd_export(extracted)
                finally:
                    shutil.rmtree(extracted, ignore_errors=True)

    def test_rejects_non_letterboxd_archive(self):
        payload = make_zip([("notes.txt", "not a Letterboxd export")])
        with tempfile.TemporaryDirectory() as root:
            with patch.object(file_service, "UPLOAD_DIR", root):
                extracted = file_service.extract_zip(payload)
                try:
                    with self.assertRaisesRegex(ValueError, "doesn't appear to be a valid Letterboxd export"):
                        file_service.validate_letterboxd_export(extracted)
                finally:
                    shutil.rmtree(extracted, ignore_errors=True)


class ProfileFavoritesTests(unittest.TestCase):
    def test_parses_favorite_links_in_original_order(self):
        favorites = [
            "https://boxd.it/1uhM",
            "https://boxd.it/2Oa4",
            "https://boxd.it/2aq2",
            "https://boxd.it/b8wK",
        ]
        profile_csv = 'Username,Favorite Films\n"example","' + ", ".join(favorites) + '"\n'

        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, "profile.csv"), "w", encoding="utf-8") as file:
                file.write(profile_csv)
            self.assertEqual(file_service.parse_profile_favorites(root), favorites)

    def test_missing_profile_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(file_service.parse_profile_favorites(root), [])


if __name__ == "__main__":
    unittest.main()
