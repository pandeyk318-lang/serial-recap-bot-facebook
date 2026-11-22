"""Facebook Page video publishing with a Page ID and Page access token."""
import os
import re

import requests

import config as S

GRAPH_VIDEO = "https://graph-video.facebook.com"


class FacebookPublishError(RuntimeError):
    def __init__(self, message, *, uncertain=False, status_code=0):
        super().__init__(message)
        self.uncertain = uncertain
        self.status_code = status_code


def _message(response, secrets):
    try:
        body = response.json()
        error = body.get("error", body)
        message = error.get("message") or str(error)
        code = error.get("code")
        if code:
            message = f"Meta API error {code}: {message}"
    except (ValueError, AttributeError):
        message = response.text[:500] or f"HTTP {response.status_code}"
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message[:500]


def _json(response, secrets, *, uncertain_on_server_error=False):
    if response.status_code < 200 or response.status_code >= 300:
        raise FacebookPublishError(
            _message(response, secrets),
            uncertain=uncertain_on_server_error and response.status_code >= 500,
            status_code=response.status_code,
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise FacebookPublishError("Meta returned invalid JSON") from exc
    if not isinstance(body, dict):
        raise FacebookPublishError("Meta returned an unexpected JSON response")
    if body.get("error"):
        raise FacebookPublishError(_message(response, secrets))
    return body


def _offsets(body, size):
    try:
        start = int(body["start_offset"])
        end = int(body["end_offset"])
    except (KeyError, TypeError, ValueError) as exc:
        raise FacebookPublishError("Meta returned invalid resumable upload offsets") from exc
    if start < 0 or end < start or end > size:
        raise FacebookPublishError("Meta returned out-of-range resumable upload offsets")
    return start, end


def publish_video(path, *, title="", description="", page_id=None, page_token=None,
                  thumbnail_path=None, version=None):
    page_id = page_id or os.getenv("FACEBOOK_PAGE_ID", "").strip()
    page_token = page_token or os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    version = version or S.META_GRAPH_API_VERSION
    if not re.fullmatch(r"v\d+\.\d+", version):
        raise FacebookPublishError("META_GRAPH_API_VERSION must look like v26.0")
    missing = [
        name for name, value in (
            ("FACEBOOK_PAGE_ID", page_id),
            ("FACEBOOK_PAGE_ACCESS_TOKEN", page_token),
        ) if not value
    ]
    if missing:
        raise FacebookPublishError("Missing required Facebook configuration: " + ", ".join(missing))
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise FacebookPublishError(f"Facebook video file is missing or empty: {path}")
    if thumbnail_path and (not os.path.isfile(thumbnail_path) or os.path.getsize(thumbnail_path) == 0):
        raise FacebookPublishError(f"Facebook thumbnail file is missing or empty: {thumbnail_path}")

    secrets = (page_token,)
    size = os.path.getsize(path)
    endpoint = f"{GRAPH_VIDEO}/{version}/{page_id}/videos"
    try:
        start_response = requests.post(
            endpoint,
            data={
                "upload_phase": "start",
                "file_size": str(size),
                "access_token": page_token,
            },
            timeout=(15, 60),
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise FacebookPublishError("Facebook upload session could not be started") from exc
    start = _json(start_response, secrets)
    session_id = start.get("upload_session_id")
    video_id = start.get("video_id")
    if not session_id or not video_id:
        raise FacebookPublishError("Meta did not return an upload session and video ID")
    start_offset, end_offset = _offsets(start, size)

    with open(path, "rb") as video:
        while start_offset < end_offset:
            video.seek(start_offset)
            chunk = video.read(end_offset - start_offset)
            if not chunk:
                raise FacebookPublishError("Could not read the next Facebook upload chunk")
            try:
                transfer_response = requests.post(
                    endpoint,
                    data={
                        "upload_phase": "transfer",
                        "upload_session_id": session_id,
                        "start_offset": str(start_offset),
                        "access_token": page_token,
                    },
                    files={"video_file_chunk": ("chunk.mp4", chunk, "application/octet-stream")},
                    timeout=(30, 600),
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                raise FacebookPublishError("Facebook upload chunk transfer failed") from exc
            transfer = _json(transfer_response, secrets)
            next_start, next_end = _offsets(transfer, size)
            if next_start <= start_offset:
                raise FacebookPublishError("Facebook upload made no progress")
            start_offset, end_offset = next_start, next_end

    finish_data = {
        "upload_phase": "finish",
        "upload_session_id": session_id,
        "title": title[:250],
        "description": description,
        "published": "true",
        "access_token": page_token,
    }
    files = None
    if thumbnail_path:
        thumbnail = open(thumbnail_path, "rb")
        files = {"thumb": ("thumb.jpg", thumbnail, "image/jpeg")}
    try:
        finish_response = requests.post(
            endpoint,
            data=finish_data,
            files=files,
            timeout=(15, 180),
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise FacebookPublishError(
            "Facebook publish request timed out; the video may already be published",
            uncertain=True,
        ) from exc
    finally:
        if files:
            thumbnail.close()

    result = _json(finish_response, secrets, uncertain_on_server_error=True)
    if result.get("success") is False:
        raise FacebookPublishError("Facebook did not confirm the video publish")
    return str(result.get("video_id") or video_id)
