import io

from django.test import SimpleTestCase
from PIL import Image

from apps.agents.utils.file_validation import validate_profile_photo


class ProfilePhotoValidationTests(SimpleTestCase):
    def _jpeg_bytes(self):
        buf = io.BytesIO()
        Image.new('RGB', (32, 32), color=(200, 100, 50)).save(buf, format='JPEG', quality=90)
        return buf.getvalue()

    def _png_bytes(self):
        buf = io.BytesIO()
        Image.new('RGBA', (32, 32), color=(200, 100, 50, 255)).save(buf, format='PNG')
        return buf.getvalue()

    def test_jpeg_with_jpg_filename(self):
        data = self._jpeg_bytes()
        ok, err, ext = validate_profile_photo(data, 'profile_photo.jpg')
        self.assertTrue(ok, err)
        self.assertEqual(ext, '.jpg')

    def test_png_bytes_wrong_jpg_filename_still_accepted(self):
        """Cropper used to send PNG data named .jpg — must not reject."""
        data = self._png_bytes()
        ok, err, ext = validate_profile_photo(data, 'profile_photo.jpg')
        self.assertTrue(ok, err)
        self.assertEqual(ext, '.png')
