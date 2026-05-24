"""U5: error bucket classification."""

from __future__ import annotations

import pytest
import yt_dlp

from yt2mp3.helpers import classify_error


@pytest.mark.parametrize(
    "exception_class,expected_bucket",
    [
        (yt_dlp.utils.DownloadError, "recoverable"),
        (yt_dlp.utils.GeoRestrictedError, "permanent"),
        (yt_dlp.utils.ExtractorError, "catastrophic"),
        (FileNotFoundError, "catastrophic"),
        (yt_dlp.utils.PostProcessingError, "permanent"),
        (OSError, "permanent"),
    ],
)
def test_error_bucket(exception_class, expected_bucket):
    try:
        e = exception_class("test message")
    except TypeError:
        # Some yt-dlp errors need richer ctor args.
        e = exception_class("test message", "msg")
    assert classify_error(e) == expected_bucket
