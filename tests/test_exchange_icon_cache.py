import base64
import threading
import time
import zlib

from src.poetore.exchange_catalog import (
    bundled_exchange_icon_path,
    divination_card_icon_path,
    placeholder_icon_path,
)
from src.poetore.exchange_icon_cache import (
    MAX_IMAGE_BYTES,
    ExchangeIconCache,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
URL = "https://web.poecdn.com/gen/image/example.png"


def test_first_request_fetches_then_same_session_uses_memory(tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        return PNG_1X1

    cache = ExchangeIconCache(tmp_path / "icons", fetcher=fetcher)
    first = cache.request("remote", URL).result(timeout=2)
    second = cache.request("remote", URL).result(timeout=2)
    cache.close()

    assert first.source == "network"
    assert first.path.read_bytes() == PNG_1X1
    assert second.source == "memory"
    assert second.path == first.path
    assert calls == [URL]


def test_restart_uses_disk_without_network(tmp_path):
    root = tmp_path / "icons"
    first = ExchangeIconCache(root, fetcher=lambda _url: PNG_1X1)
    stored = first.request("remote", URL).result(timeout=2)
    first.close()

    restarted = ExchangeIconCache(
        root,
        fetcher=lambda _url: (_ for _ in ()).throw(
            AssertionError("disk hit must not fetch")
        ),
    )
    result = restarted.request("remote", URL).result(timeout=2)
    restarted.close()

    assert result.source == "disk"
    assert result.path == stored.path


def test_same_url_concurrent_requests_share_one_fetch(tmp_path):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def fetcher(url):
        calls.append(url)
        started.set()
        release.wait(timeout=2)
        return PNG_1X1

    cache = ExchangeIconCache(tmp_path / "icons", fetcher=fetcher)
    first = cache.request("remote", URL)
    assert started.wait(timeout=2)
    second = cache.request("remote", URL)

    assert first is second
    assert not first.done()
    release.set()
    assert first.result(timeout=2).source == "network"
    cache.close()
    assert calls == [URL]


def test_changed_url_uses_a_new_stable_cache_path(tmp_path):
    calls = []
    cache = ExchangeIconCache(
        tmp_path / "icons",
        fetcher=lambda url: calls.append(url) or PNG_1X1,
    )

    first = cache.request("remote", URL).result(timeout=2)
    changed = cache.request("remote", f"{URL}?v=2").result(timeout=2)
    cache.close()

    assert first.path != changed.path
    assert calls == [URL, f"{URL}?v=2"]


def test_broken_image_is_placeholder_and_is_retried(tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        return b"not an image"

    cache = ExchangeIconCache(tmp_path / "icons", fetcher=fetcher)

    assert cache.request("remote", URL).result(timeout=2).is_placeholder
    assert cache.request("remote", URL).result(timeout=2).is_placeholder
    cache.close()
    assert calls == [URL, URL]


def test_oversized_or_huge_dimension_image_is_placeholder(tmp_path):
    huge_dimensions = bytearray(PNG_1X1)
    huge_dimensions[16:24] = (4096).to_bytes(4, "big") * 2
    huge_dimensions[29:33] = (
        zlib.crc32(bytes(huge_dimensions[12:29])) & 0xFFFFFFFF
    ).to_bytes(4, "big")
    responses = iter((b"x" * (MAX_IMAGE_BYTES + 1), bytes(huge_dimensions)))
    cache = ExchangeIconCache(
        tmp_path / "icons",
        fetcher=lambda _url: next(responses),
    )

    assert cache.request("remote", URL).result(timeout=2).is_placeholder
    assert cache.request("remote", URL).result(timeout=2).is_placeholder
    cache.close()


def test_network_failure_is_placeholder_then_can_retry(tmp_path):
    attempts = [OSError("offline"), PNG_1X1]

    def fetcher(_url):
        result = attempts.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    cache = ExchangeIconCache(tmp_path / "icons", fetcher=fetcher)
    failed = cache.request("remote", URL).result(timeout=2)
    recovered = cache.request("remote", URL).result(timeout=2)
    cache.close()

    assert failed.is_placeholder
    assert recovered.source == "network"


def test_corrupt_disk_entry_is_refetched(tmp_path):
    root = tmp_path / "icons"
    original = ExchangeIconCache(root, fetcher=lambda _url: PNG_1X1)
    path = original.request("remote", URL).result(timeout=2).path
    original.close()
    path.write_bytes(b"broken")
    calls = []
    restarted = ExchangeIconCache(
        root,
        fetcher=lambda url: calls.append(url) or PNG_1X1,
    )

    result = restarted.request("remote", URL).result(timeout=2)
    restarted.close()

    assert result.source == "network"
    assert result.path.read_bytes() == PNG_1X1
    assert calls == [URL]


def test_divination_card_uses_bundled_asset_without_network(tmp_path):
    cache = ExchangeIconCache(
        tmp_path / "icons",
        fetcher=lambda _url: (_ for _ in ()).throw(
            AssertionError("bundled icon must not fetch")
        ),
    )

    result = cache.request("divination_card").result(timeout=1)
    cache.close()

    assert result.source == "bundled"
    assert result.path == divination_card_icon_path()
    assert result.path.is_file()


def test_confirmed_exchange_items_use_their_bundled_assets_without_network(tmp_path):
    cache = ExchangeIconCache(
        tmp_path / "icons",
        fetcher=lambda _url: (_ for _ in ()).throw(
            AssertionError("bundled icon must not fetch")
        ),
    )

    for filename in (
        "TriskelionShattered.png",
        "TriskelionReforged.png",
        "MessageInABottle.png",
    ):
        result = cache.request("bundled", icon_filename=filename).result(timeout=1)
        assert result.source == "bundled"
        assert result.path == bundled_exchange_icon_path(filename)
        assert result.image_format == "png"
    cache.close()


def test_unknown_bundled_icon_uses_placeholder(tmp_path):
    cache = ExchangeIconCache(tmp_path / "icons")
    result = cache.request("bundled", icon_filename="../outside.png").result(timeout=1)
    cache.close()

    assert result.is_placeholder
    assert result.path == placeholder_icon_path()


def test_missing_or_untrusted_remote_url_uses_bundled_placeholder(tmp_path):
    cache = ExchangeIconCache(tmp_path / "icons")

    missing = cache.request("remote", None).result(timeout=1)
    untrusted = cache.request("remote", "https://example.invalid/icon.png").result(
        timeout=1
    )
    cache.close()

    assert missing.path == placeholder_icon_path()
    assert missing.is_placeholder
    assert untrusted.path == placeholder_icon_path()
    assert untrusted.is_placeholder


def test_network_fetch_never_runs_on_requesting_thread(tmp_path):
    caller_thread = threading.get_ident()
    fetch_thread = []
    release = threading.Event()

    def fetcher(_url):
        fetch_thread.append(threading.get_ident())
        release.wait(timeout=2)
        return PNG_1X1

    cache = ExchangeIconCache(tmp_path / "icons", fetcher=fetcher)
    started_at = time.perf_counter()
    future = cache.request("remote", URL)
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.1
    assert not future.done()
    release.set()
    future.result(timeout=2)
    cache.close()
    assert fetch_thread != [caller_thread]
