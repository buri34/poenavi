from dataclasses import dataclass
import json
import os
import re
from urllib.parse import quote
import urllib.request

from src.update.release_channel import (
    load_release_repository,
    release_by_tag_api_url,
    releases_api_url,
    releases_page_url,
)

TEST_RELEASE_TAG_ENV = "POENAVI_UPDATE_TEST_TAG"
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    notes: str
    page_url: str
    zip_url: str
    checksum_url: str


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError(f"不正なバージョン形式です: {value}")
    return tuple(int(part) for part in match.groups())


def parse_latest_release(
    payload: dict,
    current_version: str,
    *,
    allow_prerelease: bool = False,
    repository: str | None = None,
) -> ReleaseInfo | None:
    if payload.get("draft") or (payload.get("prerelease") and not allow_prerelease):
        return None

    tag = str(payload.get("tag_name", ""))
    try:
        latest = parse_version(tag)
        current = parse_version(current_version)
    except ValueError:
        return None
    if latest <= current:
        return None

    assets = {
        asset.get("name"): asset.get("browser_download_url")
        for asset in payload.get("assets", [])
    }
    zip_url = assets.get("PoENavi.zip")
    checksum_url = assets.get("PoENavi.zip.sha256")
    if not zip_url or not checksum_url:
        return None

    return ReleaseInfo(
        version=".".join(str(part) for part in latest),
        notes=str(payload.get("body") or "変更内容はリリースページで確認できます。"),
        page_url=str(
            payload.get("html_url")
            or releases_page_url(repository)
        ),
        zip_url=str(zip_url),
        checksum_url=str(checksum_url),
    )


def fetch_latest_release(
    current_version: str,
    opener=urllib.request.urlopen,
    *,
    repository: str | None = None,
) -> ReleaseInfo | None:
    repository = repository or load_release_repository()
    test_tag = os.environ.get(TEST_RELEASE_TAG_ENV, "").strip()
    allow_prerelease = False
    release_api = releases_api_url(repository)
    if test_tag:
        # 明示したテスト起動だけ、指定タグのPre-releaseを参照する。
        # 通常起動では従来どおり /releases/latest の正式版のみが対象。
        parse_version(test_tag)
        release_api = release_by_tag_api_url(
            quote(test_tag, safe=""),
            repository,
        )
        allow_prerelease = True

    request = urllib.request.Request(
        release_api,
        headers={"User-Agent": "PoENavi-Updater"},
    )
    with opener(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_latest_release(
        payload,
        current_version,
        allow_prerelease=allow_prerelease,
        repository=repository,
    )
