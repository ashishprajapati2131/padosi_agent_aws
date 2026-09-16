"""
Custom storage backend for WhiteNoise that runs static-file compression
synchronously (single-threaded) to support shared hosting environments
(e.g. CloudLinux / cPanel) that impose strict OS thread limits.

Root cause: whitenoise.storage.CompressedManifestStaticFilesStorage uses
ThreadPoolExecutor inside compress_files(). On restricted hosts the OS
raises "RuntimeError: can't start new thread" when the executor tries to
spawn worker threads during `collectstatic`.

Fix: override compress_files() with an identical implementation that
iterates over files sequentially instead of using a thread pool.
"""

from django.conf import settings
from whitenoise.storage import CompressedManifestStaticFilesStorage


class SingleThreadedCompressedManifestStaticFilesStorage(
    CompressedManifestStaticFilesStorage
):
    """
    Drop-in replacement for WhiteNoise's CompressedManifestStaticFilesStorage
    that compresses static files one-by-one (no threads) and gracefully falls back
    if a static file is missing from manifest or STATIC_ROOT instead of throwing 500 errors.
    """
    manifest_strict = False

    def stored_name(self, name):
        try:
            return super().stored_name(name)
        except Exception:
            return name

    def url(self, name, force=False):
        try:
            return super().url(name, force=force)
        except Exception:
            prefix = getattr(settings, "STATIC_URL", "/static/").rstrip("/")
            clean_name = name.lstrip("/ ")
            return f"{prefix}/{clean_name}"

    def compress_files(self, paths):
        extensions = getattr(settings, "WHITENOISE_SKIP_COMPRESS_EXTENSIONS", None)
        self.compressor = self.create_compressor(extensions=extensions, quiet=True)

        for path in paths:
            if not self.compressor.should_compress(path):
                continue
            full_path = self.path(path)
            prefix_len = len(full_path) - len(path)
            for compressed_path in self.compressor.compress(full_path):
                compressed_name = compressed_path[prefix_len:]
                yield path, compressed_name
