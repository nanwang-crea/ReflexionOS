from collections.abc import Mapping


_BROWSER_LIKE_HEADERS = {
    "User-Agent": (
        "claude-cli/2.1.177"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    # "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}


def browser_like_default_headers() -> Mapping[str, str]:
    return dict(_BROWSER_LIKE_HEADERS)
