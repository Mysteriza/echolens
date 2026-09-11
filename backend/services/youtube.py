import logging
import time

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.config import settings
from core.validation import extract_video_id

logger = logging.getLogger(__name__)

__all__ = ["YouTubeService", "extract_video_id"]


class YouTubeService:
    def __init__(self):
        if not settings.YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY is not set")
        self.youtube = build("youtube", "v3", developerKey=settings.YOUTUBE_API_KEY)

    def _execute_with_retry(self, request, attempts: int = 4):
        """Execute a Google API request with exponential backoff on quota/5xx."""
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                return request.execute()
            except HttpError as exc:
                last_exc = exc
                status = getattr(exc.resp, "status", 0)
                # Retry rate limits and server errors; fail fast otherwise.
                if status in (403, 429, 500, 502, 503) and attempt < attempts - 1:
                    logger.warning(
                        "YouTube API HTTP %s (attempt %d/%d). Retrying in %.1fs",
                        status,
                        attempt + 1,
                        attempts,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
            except (OSError, TimeoutError) as exc:
                last_exc = exc
                if attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError("YouTube request failed without response.")

    def get_video_metadata(self, video_id: str) -> dict:
        request = self.youtube.videos().list(part="snippet,statistics", id=video_id)
        try:
            response = self._execute_with_retry(request)
        except HttpError as exc:
            status = getattr(exc.resp, "status", 0)
            if status == 404:
                raise ValueError("Video not found") from exc
            logger.error("YouTube metadata error: %s", exc)
            raise ValueError("Failed to fetch video metadata.") from exc

        if not response.get("items"):
            raise ValueError("Video not found")

        item = response["items"][0]
        snippet = item["snippet"]
        statistics = item["statistics"]

        return {
            "youtube_id": video_id,
            "title": snippet.get("title"),
            "channel": snippet.get("channelTitle"),
            "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
            "comment_count": int(statistics.get("commentCount", 0)),
        }

    def get_comments(self, video_id: str, max_results: int = 100) -> list:
        comments: list[dict] = []
        try:
            request = self.youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=min(100, max_results),
                textFormat="plainText",
            )

            while request and len(comments) < max_results:
                try:
                    response = self._execute_with_retry(request)
                except HttpError as exc:
                    status = getattr(exc.resp, "status", 0)
                    if status in (403, 404):
                        # Comments disabled / not found: return what we have.
                        logger.warning(
                            "YouTube comments unavailable (HTTP %s). Returning %d collected.",
                            status,
                            len(comments),
                        )
                        break
                    raise

                for item in response.get("items", []):
                    top_level = item["snippet"]["topLevelComment"]
                    comments.append(
                        {
                            "youtube_id": top_level["id"],
                            "parent_id": None,
                            "author_name": top_level["snippet"].get(
                                "authorDisplayName"
                            ),
                            "text": top_level["snippet"].get("textDisplay"),
                            "published_at": top_level["snippet"].get("publishedAt"),
                            "like_count": top_level["snippet"].get("likeCount", 0),
                            "is_reply": False,
                        }
                    )

                    if len(comments) >= max_results:
                        break

                    # Handle replies if available
                    if "replies" in item:
                        for reply in item["replies"].get("comments", []):
                            comments.append(
                                {
                                    "youtube_id": reply["id"],
                                    "parent_id": top_level["id"],
                                    "author_name": reply["snippet"].get(
                                        "authorDisplayName"
                                    ),
                                    "text": reply["snippet"].get("textDisplay"),
                                    "published_at": reply["snippet"].get("publishedAt"),
                                    "like_count": reply["snippet"].get("likeCount", 0),
                                    "is_reply": True,
                                }
                            )
                            if len(comments) >= max_results:
                                break

                if len(comments) < max_results and "nextPageToken" in response:
                    request = self.youtube.commentThreads().list(
                        part="snippet,replies",
                        videoId=video_id,
                        pageToken=response["nextPageToken"],
                        maxResults=min(100, max_results - len(comments)),
                        textFormat="plainText",
                    )
                else:
                    break
        except Exception as exc:  # noqa: BLE001 - return partial results, never crash
            logger.error("Error fetching comments: %s", exc)

        return comments
