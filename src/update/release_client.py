from dataclasses import dataclass
import json
import re
import urllib.request


RELEASES_API = "https://api.github.com/repos/buri34/poenavi/releases/latest"
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


def parse_latest_release(payload: dict, current_version: str) -> ReleaseInfo | None:
    if payload.get("draft") or payload.get("prerelease"):
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
            or "https://github.com/buri34/poenavi/releases/latest"
        ),
        zip_url=str(zip_url),
        checksum_url=str(checksum_url),
    )


def fetch_latest_release(
    current_version: str,
    opener=urllib.request.urlopen,
) -> ReleaseInfo | None:
    request = urllib.request.Request(
        RELEASES_API,
        headers={"User-Agent": "PoENavi-Updater"},
    )
    with opener(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_latest_release(payload, current_version)
