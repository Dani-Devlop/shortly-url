"""User-agent classification for click analytics.

Derives a coarse device class from the ``User-Agent`` header. The goal is a
small, stable vocabulary — ``desktop | mobile | tablet | bot | other`` — that
aggregates cleanly and never leaks long UA strings into query results.
"""

import re

# Detection order matters: bots first (they often fake browser tokens), then
# tablet (iPads also say "Mobile" on iOS 13+), then mobile, then desktop hints.
_BOT_PATTERN = re.compile(
    r"bot|crawl|spider|slurp|curl|wget|python-requests|httpclient|headless"
    r"|facebookexternalhit|linkedinbot|twitterbot|whatsapp|telegrambot|discordbot"
    r"|google-apis-clients|adsbot|mediapartners|bingpreview|yandex|baidu|duckduck",
    re.IGNORECASE,
)
_TABLET_PATTERN = re.compile(r"iPad|Tablet|PlayBook|Silk|Kindle|Nexus (?:7|9|10)", re.IGNORECASE)
_MOBILE_PATTERN = re.compile(
    r"Mobi|iPhone|iPod|Android.*Mobile|Windows Phone|IEMobile|BlackBerry|Opera Mini",
    re.IGNORECASE,
)
_DESKTOP_PATTERN = re.compile(r"Windows NT|Macintosh|Mac OS X|X11; Linux|CrOS", re.IGNORECASE)

DEVICE_CLASSES = ("desktop", "mobile", "tablet", "bot", "other")


def classify_user_agent(user_agent: str | None) -> str:
    """Map a raw ``User-Agent`` string to a coarse device class.

    ``None``/empty → ``other`` (we still keep the click, just unclassified).
    """
    if not user_agent or not user_agent.strip():
        return "other"
    ua = user_agent.strip()
    if _BOT_PATTERN.search(ua):
        return "bot"
    if _TABLET_PATTERN.search(ua):
        return "tablet"
    if _MOBILE_PATTERN.search(ua):
        return "mobile"
    if _DESKTOP_PATTERN.search(ua):
        return "desktop"
    return "other"
