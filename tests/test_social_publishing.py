import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "recap"))

import facebook
import publishing_state


class FakeResponse:
    def __init__(self, body, status_code=200):
        self.body = body
        self.status_code = status_code
        self.text = json.dumps(body)

    def json(self):
        return self.body


class PublishingStateTests(unittest.TestCase):
    def test_facebook_status_is_persistent_and_retryable_only_after_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            publishing_state.update("kaisi", "source-1", "facebook", "failed", error="permission denied", base=folder)
            self.assertEqual(publishing_state.platform_status("kaisi", "source-1", "facebook", folder), "failed")
            self.assertEqual(publishing_state.failed_platforms("kaisi", ["facebook"], folder), "source-1")

            publishing_state.update("kaisi", "source-1", "facebook", "success", media_id="fb-1", base=folder)
            self.assertEqual(publishing_state.failed_platforms("kaisi", ["facebook"], folder), "")
            entry = publishing_state.get_entry("kaisi", "source-1", folder)
            self.assertEqual(entry["platforms"]["facebook"]["media_id"], "fb-1")

    def test_uncertain_result_is_not_returned_for_automatic_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            publishing_state.update("kaisi", "source-1", "facebook", "uncertain", base=folder)
            self.assertEqual(publishing_state.failed_platforms("kaisi", ["facebook"], folder), "")

    def test_concurrent_workers_can_claim_a_destination_only_once(self):
        with tempfile.TemporaryDirectory() as folder:
            with ThreadPoolExecutor(max_workers=8) as pool:
                claimed = list(pool.map(
                    lambda _: publishing_state.claim("kaisi", "source-1", "facebook", base=folder),
                    range(8),
                ))
            self.assertEqual(sum(claimed), 1)
            self.assertEqual(publishing_state.get_entry("kaisi", "source-1", folder)
                             ["platforms"]["facebook"]["attempts"], 1)


class FacebookPublisherTests(unittest.TestCase):
    def test_resumable_upload_handle_is_published_to_configured_page(self):
        with tempfile.TemporaryDirectory() as folder:
            video_path = Path(folder) / "landscape.mp4"
            video_path.write_bytes(b"synthetic-video")
            responses = [
                FakeResponse({"id": "upload:session-1"}),
                FakeResponse({"h": "uploaded-handle"}),
                FakeResponse({"id": "page-video-1"}),
            ]
            with mock.patch.object(facebook.requests, "post", side_effect=responses) as post:
                video_id = facebook.publish_video(
                    str(video_path),
                    title="Title",
                    description="Description",
                    page_id="page-1",
                    page_token="page-token",
                    app_id="app-1",
                    user_token="user-token",
                    version="v26.0",
                )

        self.assertEqual(video_id, "page-video-1")
        self.assertTrue(post.call_args_list[0].args[0].endswith("/v26.0/app-1/uploads"))
        self.assertEqual(post.call_args_list[0].kwargs["params"]["file_length"], "15")
        self.assertEqual(post.call_args_list[1].kwargs["headers"]["file_offset"], "0")
        self.assertEqual(post.call_args_list[2].args[0], "https://graph-video.facebook.com/v26.0/page-1/videos")
        self.assertEqual(post.call_args_list[2].kwargs["data"]["fbuploader_video_file_chunk"], "uploaded-handle")
        self.assertEqual(post.call_args_list[2].kwargs["data"]["access_token"], "page-token")

    def test_api_error_redacts_access_tokens(self):
        response = FakeResponse({"error": {"message": "bad token secret-value"}}, status_code=400)
        with self.assertRaises(facebook.FacebookPublishError) as raised:
            facebook._json(response, ("secret-value",))
        self.assertNotIn("secret-value", str(raised.exception))

    def test_transient_chunk_failure_resumes_at_verified_offset(self):
        with tempfile.TemporaryDirectory() as folder:
            video_path = Path(folder) / "landscape.mp4"
            video_path.write_bytes(b"synthetic-video")
            responses = [
                FakeResponse({"id": "upload:session-2"}),
                FakeResponse({"error": {"message": "temporary failure"}}, status_code=500),
                FakeResponse({"h": "resumed-handle"}),
                FakeResponse({"id": "page-video-2"}),
            ]
            with mock.patch.object(facebook.requests, "post", side_effect=responses) as post, \
                    mock.patch.object(facebook.requests, "get", return_value=FakeResponse({"file_offset": 0})) as get, \
                    mock.patch.object(facebook.time, "sleep"):
                video_id = facebook.publish_video(
                    str(video_path), page_id="page-1", page_token="page-token",
                    app_id="app-1", user_token="user-token",
                )
        self.assertEqual(video_id, "page-video-2")
        self.assertEqual(get.call_count, 1)
        self.assertEqual(post.call_args_list[2].kwargs["headers"]["file_offset"], "0")

    def test_missing_credentials_and_video_are_reported(self):
        with self.assertRaisesRegex(facebook.FacebookPublishError, "META_USER_ACCESS_TOKEN"):
            facebook.publish_video("missing.mp4", page_id="page", page_token="token", app_id="app", user_token="")


if __name__ == "__main__":
    unittest.main()
