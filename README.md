# Serial Recap Bot — Facebook Page Edition

Generates Hindi motion-comic recaps of Dangal TV serial episodes and publishes them to **one Facebook Page only**.

The official YouTube channel is used solely as the source for episode discovery and analysis (public channel RSS, episode pages, and thumbnails). This repository has no YouTube upload path or Instagram publishing/rendering path. Recap MP4 files are landscape 1920 × 1080.

## What it does

- Finds recent full episodes for nine configured shows from the Dangal TV public feed.
- Uses Gemini to analyze the episode and write the Hindi recap and next-episode prediction.
- Creates original illustrations, Hindi narration, captions, and a landscape MP4.
- Publishes the MP4 and description to the configured Facebook Page using Meta's resumable upload flow.
- Tracks processed source episodes and Facebook publishing results to avoid duplicate posts.
- Retries a failed show job once in GitHub Actions. A watchdog can dispatch only the failed show again.

Facebook posts publish when the workflow runs; they are not scheduled to each show's former YouTube time slot. The Apps Script trigger runs near midnight IST and starts all nine shows. Set up the Page, API permissions, credentials, and test run before enabling the trigger.

| Show key | Serial |
| --- | --- |
| `kaisi` | Kaisi Teri Dillagi |
| `bhabhi` | Hamari Bhabhi Number 1 |
| `sohni` | Sohni Aur Nahi Koi Honi |
| `rimjhim` | Rimjhim Choti Umar Bada Safar |
| `mannsundar` | Mann Sundar |
| `atisundar` | Mann Atisundar |
| `patibrahma` | Pati Brahmachari |
| `ishq` | Ishq Junooni |
| `saanche` | Saanche Darbar Ki Jai Dhyanu Bhagat Ki Amar Kahani |

## 1. Configure GitHub Actions

In the repository, open **Settings → Secrets and variables → Actions**.

Add these **repository variables**:

| Variable | Value |
| --- | --- |
| `FACEBOOK_ENABLED` | `true` after the test succeeds; leave unset/`false` to prevent publishing |
| `META_GRAPH_API_VERSION` | Optional; defaults to `v26.0` |
| `FACEBOOK_DESCRIPTION` | Optional description override; supports `{title}`, `{description}`, `{show}`, `{episode}`, `{hook}` |
| `HF_FLUX_SPACE` | Optional image-generation fallback override |
| `SERIAL_CHANNEL_NAME` | Optional channel name used in the video |
| `SERIAL_VOICE` | Optional Edge TTS voice; default is `hi-IN-SwaraNeural` |
| `MUSIC_VOLUME` | Optional background music level |

Add these **repository secrets**:

| Secret | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Episode analysis and Hindi script |
| `FACEBOOK_PAGE_ID` | Numeric ID of the destination Page |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Publishes video posts to the Page |
| `CLOUDFLARE_ACCOUNT_ID` | Optional illustration-generation fallback |
| `CLOUDFLARE_API_TOKEN` | Optional illustration-generation fallback |
| `POLLINATIONS_TOKEN` | Optional image-generation fallback |

Never commit access tokens or put them in repository variables. `.env.example` contains names only.

## 2. Configure Facebook / Meta

1. In Meta for Developers, create or select an app and configure Facebook Page video publishing.
2. Use a Page where the authorizing person has permission to create Page content. Grant the required Page access, including `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts` as requested by the current Meta authorization flow.
3. Obtain the Page ID and a Page access token with permission to publish Page videos.
4. Add only `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN` as repository secrets. Follow Meta's token renewal guidance and renew the Page token before expiration.
5. In **Actions → Facebook serial recaps → Run workflow**, select `validate_facebook_tokens` and run it. This is read-only and does not publish.

The Facebook publisher uses Meta's three-phase resumable video upload and Page video endpoint, authenticated only with `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN`. Failures are recorded per episode. Definite failures may be retried; uncertain upload outcomes are not blindly retried to avoid duplicate posts. Check the Page before manually retrying an uncertain result.

## 3. Test before enabling automatic publishing

Run the workflow manually for a single show:

1. Select one value for `only_show`.
2. Set `test_mode` to `true` and leave `upload` as `false`.
3. Check the generated output artifact and the job logs.
4. When ready to publish, set `test_mode` to `false`, `upload` to `true`, and `FACEBOOK_ENABLED` to `true`.

The test render still calls the configured generation services but does not publish. A normal run without Facebook publishing enabled renders locally and saves its result without posting.

## 4. Set up the daily trigger (Google Apps Script)

The workflow has no GitHub cron. Use the checked-in [`scheduler/google_apps_script.gs`](./scheduler/google_apps_script.gs) for the midnight IST dispatcher and two-hour failure watchdog.

1. Open [script.google.com](https://script.google.com), create a project, and paste the checked-in script into `Code.gs`.
2. In **Project Settings → Script properties**, add `GITHUB_PAT`. Use a fine-grained token scoped to this repository with **Actions: read and write** permission.
3. Run `setupTriggers()` once and authorize the requested permissions.
4. Check Apps Script **Executions** and GitHub Actions runs after the first trigger.

The script is configured for `pandeyk318-lang/serial-recap-bot-facebook`. The nightly workflow publishes to Facebook as each show finishes; the trigger does not schedule future Facebook publication times. To stop automated runs, delete the Apps Script triggers or set `FACEBOOK_ENABLED` to `false`.

## Local setup

Install Python dependencies and FFmpeg. On Ubuntu/GitHub Actions, the workflow installs FFmpeg, Noto Devanagari fonts, Pillow RAQM libraries, and Playwright Chromium. On Windows, install FFmpeg and ensure `ffmpeg` and `ffprobe` are on `PATH`; use a Pillow build with RAQM support.

```powershell
python -m pip install -r requirements.txt
```

The application reads configuration from its process environment; it does not automatically load `.env`. Run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

Tests mock Meta APIs and use synthetic media. They do not require credentials or publish content.

## State and recovery

- `state/<show>.json` stores processed source video and episode identifiers.
- `state/<show>_publishing.json` stores Facebook post status, attempt count, media ID, timestamp, and error.
- `state/<show>_status.json` stores the latest workflow status and log summary.

Successful posts are skipped on retry. `failed` is eligible for a later retry; `uncertain` and stale `in_progress` require manual Page verification before changing state. Never clear publishing state just to retry.

For troubleshooting, inspect the GitHub Actions job log and the matching state file. Common problems include missing Page tasks/permissions, expired or revoked tokens (Meta error 190), and image-generation provider quotas. Fix the underlying issue before retrying.
