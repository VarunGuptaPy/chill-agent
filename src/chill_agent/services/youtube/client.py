"""YouTube Data API v3 client with OAuth 2.0."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

# Cost tracking: YouTube API quota units
QUOTA_UPLOAD = 1600
QUOTA_THUMBNAIL = 50
QUOTA_ANALYTICS = 1


class YouTubeClient:
    def __init__(
        self,
        client_secrets_file: Path,
        token_file: Path,
    ) -> None:
        self._client_secrets_file = client_secrets_file
        self._token_file = token_file
        self._service = None
        self._analytics_service = None

    def _get_credentials(self) -> Credentials:
        creds = None

        if self._token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self._token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self._client_secrets_file.exists():
                    raise FileNotFoundError(
                        f"YouTube client secrets not found: {self._client_secrets_file}\n"
                        "Run 'chill-agent init' to set up OAuth."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._client_secrets_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_file, "w") as f:
                f.write(creds.to_json())

        return creds

    def _get_service(self):
        if self._service is None:
            creds = self._get_credentials()
            self._service = build("youtube", "v3", credentials=creds)
        return self._service

    def _get_analytics_service(self):
        if self._analytics_service is None:
            creds = self._get_credentials()
            self._analytics_service = build("youtubeAnalytics", "v2", credentials=creds)
        return self._analytics_service

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        publish_at: datetime,
        category_id: str = "27",
    ) -> str:
        """Upload video as private + scheduled. Returns YouTube video ID."""
        service = self._get_service()

        # Ensure timezone-aware datetime
        if publish_at.tzinfo is None:
            from datetime import timezone
            publish_at = publish_at.replace(tzinfo=timezone.utc)

        publish_at_str = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:500],
                "categoryId": category_id,
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at_str,
                "madeForKids": False,
                "selfDeclaredMadeForKids": False,
                "containsSyntheticMedia": True,  # CRITICAL: AI disclosure
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        logger.info(
            "youtube_upload_start",
            title=title,
            publish_at=publish_at_str,
            file_size_mb=round(video_path.stat().st_size / 1024 / 1024, 1),
        )

        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.debug("youtube_upload_progress", percent=int(status.progress() * 100))

        video_id = response["id"]
        logger.info("youtube_upload_done", video_id=video_id)
        return video_id

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> None:
        """Upload thumbnail for a video. Retries with backoff — YouTube often
        needs a few seconds after video upload before accepting thumbnails."""
        import time
        from googleapiclient.errors import HttpError

        service = self._get_service()
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")

        backoff = (5.0, 15.0, 30.0)
        last_exc: Exception | None = None
        for attempt, wait in enumerate(backoff, start=1):
            try:
                service.thumbnails().set(videoId=video_id, media_body=media).execute()
                logger.info("youtube_thumbnail_set", video_id=video_id, attempt=attempt)
                return
            except HttpError as exc:
                last_exc = exc
                # 403 = channel not eligible for custom thumbnails — pointless to retry
                if exc.resp.status == 403:
                    logger.error(
                        "youtube_thumbnail_not_eligible",
                        video_id=video_id,
                        error=str(exc),
                        hint="Channel needs 1000 subs or verification for custom thumbnails",
                    )
                    raise
                logger.warning(
                    "youtube_thumbnail_retry",
                    video_id=video_id,
                    attempt=attempt,
                    wait_seconds=wait,
                    status=exc.resp.status,
                    error=str(exc),
                )
                time.sleep(wait)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "youtube_thumbnail_retry",
                    video_id=video_id,
                    attempt=attempt,
                    wait_seconds=wait,
                    error=str(exc),
                )
                time.sleep(wait)

        raise last_exc  # type: ignore[misc]

    def get_video_stats(self, video_ids: List[str]) -> List[dict]:
        """Fetch view/like/comment stats for a list of video IDs."""
        service = self._get_service()
        result = (
            service.videos()
            .list(
                part="statistics",
                id=",".join(video_ids),
            )
            .execute()
        )
        return result.get("items", [])

    def get_analytics(
        self,
        channel_id: str,
        video_ids: List[str],
        start_date: str,
        end_date: str,
    ) -> dict:
        """Fetch CTR and AVD from YouTube Analytics API."""
        analytics = self._get_analytics_service()
        try:
            response = (
                analytics.reports()
                .query(
                    ids=f"channel=={channel_id}",
                    startDate=start_date,
                    endDate=end_date,
                    metrics="views,estimatedMinutesWatched,averageViewDuration,clickThroughRate",
                    dimensions="video",
                    filters=f"video=={','.join(video_ids)}",
                )
                .execute()
            )
            return response
        except Exception as e:
            logger.error("youtube_analytics_failed", error=str(e))
            return {}
