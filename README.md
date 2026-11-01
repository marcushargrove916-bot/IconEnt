# IconEnt · ONE HIT WONDER — STREET CINEMA

**Owner-operated AI movie studio for realistic fictional street dramas, action scenes, music videos and romance.** Works in Safari on iPhone once hosted.

## New Street Cinema features

- **Upload your own cast photos:** up to 24 JPG/PNG/WebP photos in a private single-user library; select up to 3 per generated scene. iPhone camera photos are converted to smaller JPG files in the browser. A user acknowledgment confirms they own the images or have people's permission to use them.
- **Quick Clip:** create an AI clip using text, one starting photo, or multiple visual reference photos.
- **Street Movie:** type a plot, pick a genre/style and 3, 5 or 8 shots, auto-build a storyboard of editable scene directions, then render scenes sequentially. Movie scenes are merged into one MP4 through FFmpeg. The original finished scenes are downloadable individually.
- **Audio:** the model can create ambient audio/dialogue from a prompt. Describe the spoken words and sounds in your scene instructions.
- **Cinematic options:** 9:16 or 16:9, 3–10 seconds per scene (UI offers 5, 8, 10), and 360p/720p/1080p resolution. Quick Clips also offer 4K.
- **Save your work:** local job history, individual scenes and merged movies (storage may be lost on free cloud hosts).
- **Private by default:** use the `APP_PASSWORD` environment variable. Photos and secrets never belong in the GitHub repository.

Each film is a **short multi-scene film** of roughly 15–80 seconds, **not** an unlimited-length theatrical film. Scene continuity and likeness are best-effort, not guaranteed. This application does not bypass the video provider's safety requirements. It allows creative street drama, fictional tension and mature storytelling *as permitted by the provider*, without promising unrestricted output. Don't create deceptive, non-consensual likeness videos of others.

## AI engine

The app calls fal.ai's `google/gemini-omni-flash/v1.1` endpoints:

- Text: `text-to-video`
- One photo: `image-to-video`
- Multiple photos: `reference-to-video`

The browser never receives the `FAL_KEY`: it's held only by the Python server. Reference images are transmitted as Base64 data URIs with the model request, not exposed on a public upload endpoint. Provider terms and safety filters apply. A movie's 8 scenes consume 8 separately billed AI generations, so understand estimated cost before starting. The price displayed is only an estimate; check [fal.ai pricing](https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video) for updates.

## Run locally

Requires Python 3.10+. To assemble finished movies, also requires FFmpeg (or `imageio-ffmpeg`).

```bash
cd one_hit_wonder
python3 -m pip install -r requirements.txt
export APP_PASSWORD='a strong private password'
export FAL_KEY='your-secret-fal-key'
python3 server.py
```

Open `http://127.0.0.1:8080` in your web browser. If no `FAL_KEY` is configured, the site loads and photos/storyboards work, but **paid AI renders are disabled**.

## Deploy to Render

Source repository: `marcushargrove916-bot/IconEnt`.

If this app is stored as `one-hit-wonder.tar.gz` in that GitHub repository, use:

| Setting | Value |
|--|--|
| Runtime | Python |
| Build command | `tar -xzf one-hit-wonder.tar.gz && pip install -r requirements.txt` |
| Start command | `python3 server.py` |
| Health-check path | `/healthz` |
| Plan | Free for testing, subject to Render billing requirements |
| Environment | `HOST=0.0.0.0`, secret `APP_PASSWORD`, secret `FAL_KEY` |

**Hosting blocker:** An attempted Render deployment previously returned HTTP 402 (“Payment information is required”). The user must add billing details *directly on Render* before Render will allow a web service. We cannot do that for them. Hosting the app does not grant AI credits; fal.ai billing is separate.

**Important:** Free-host files are ephemeral. Photos, generated scenes and saved jobs can be lost on any restart/redeploy. For production use, attach persistent storage and real user authentication, add an abuse/spend limit and background job queue, and verify video model/provider policy. `APP_PASSWORD` protects all endpoints with HTTP Basic Auth over HTTPS, suitable for private owner testing only. No public signup or unrestricted public generation is implemented.

## API endpoints

- `GET /healthz` — public status (no secrets)
- `GET /api/config`, `GET /api/jobs`, `GET /api/jobs/{uuid}` — authenticated status
- `POST /api/photos` — authenticated raw JPG/PNG/WebP upload, up to 3MB; requires `X-Photo-Consent: yes`
- `GET /api/photos`, `GET /api/photos/{uuid}`, `DELETE /api/photos/{uuid}` — private cast library
- `POST /api/jobs` — text/photo clip generation
- `POST /api/movies` — multi-scene movie generation
- `GET /api/video/{uuid}` — playable/downloadable MP4 with Safari HTTP Range support
- `GET /api/video/{uuid}/scene/{1..8}` — individual generated shot

## Safety and privacy

- Only upload photos you own or are permitted to use. For other identifiable people, get their permission.
- Never put your `FAL_KEY`, passwords or real people’s photos in a public GitHub repository.
- This app contains no switch to disable third-party safety filtering; provider restrictions are enforced by the provider.
- Generated video and audio may be inaccurate, including facial likeness, dialogue and continuity. Clearly label fictional AI depictions when appropriate.
- Rendering is costly and can take a long time. A model rejection may still incur provider charges; check your fal.ai dashboard.
