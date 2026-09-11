"""YouTube URL validation with allowlisted hosts and strict video-ID checks."""
from urllib.parse import parse_qs, urlparse

ALLOWED_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIDEO_ID_LENGTH = 11


def extract_video_id(url: str) -> str:
    """Extract and validate an 11-char YouTube video ID. Raises ValueError."""
    url = (url or "").strip()
    if not url.lower().startswith("https://"):
        raise ValueError("URL must use HTTPS.")
    try:
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Malformed URL.") from exc

    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError("URL host is not an allowed YouTube domain.")

    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0] if parsed.path else ""
    else:
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            candidate = qs["v"][0]
        else:
            # /embed/<id>, /shorts/<id>, /live/<id>
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"}:
                candidate = parts[1]

    candidate = candidate.strip()
    if len(candidate) != VIDEO_ID_LENGTH or not all(
        c.isalnum() or c in "-_" for c in candidate
    ):
        raise ValueError("Could not extract a valid video ID from URL.")
    return candidate
