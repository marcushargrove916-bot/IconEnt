#!/usr/bin/env python3
"""One Hit Wonder • Street Cinema, an owner-operated AI video studio.

Creates individual clips or an editable scene-by-scene short movie with photos
supplied by the user. The video model and provider apply their own policies.
Provider credentials stay on the server and are never returned to browsers.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4
import business

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", str(ROOT))).expanduser()
DATA, VIDEOS, PHOTOS = (STORAGE_ROOT / n for n in ("data", "videos", "photos"))
for folder in (DATA, VIDEOS, PHOTOS):
    folder.mkdir(parents=True, exist_ok=True)
JOBS_FILE, PHOTOS_FILE = DATA / "jobs.json", DATA / "photos.json"
TEXT_MODEL = "google/gemini-omni-flash/v1.1/text-to-video"
IMAGE_MODEL = "google/gemini-omni-flash/v1.1/image-to-video"
REFERENCE_MODEL = "google/gemini-omni-flash/v1.1/reference-to-video"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))
FAL_KEY = os.getenv("FAL_KEY", "").strip()
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
BUSINESS_MODE = os.getenv("BUSINESS_MODE", "0") == "1"
MAX_RUNNING = 2
MAX_HISTORY = 70
MAX_VIDEO_BYTES = 150 * 1024 * 1024
MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_PHOTOS_PER_JOB = 3
MAX_PHOTO_LIBRARY = 24
MAX_SCENES = 8
RATES = {"360p": 0.03, "720p": 0.10, "1080p": 0.15, "4k": 0.30}
GENRES = ("Street crime drama", "Neighborhood family drama", "Romance & betrayal", "Fictional heist thriller", "Hip-hop music drama", "Action thriller")
TONES = ("Gritty realistic", "Film noir", "Blockbuster cinematic", "Found-footage realism", "90s street-film")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOCK = threading.RLock()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_db(path: Path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        logging.exception("Unable to load %s", path)
        return {}


JOBS = load_db(JOBS_FILE)
PHOTO_LIBRARY = load_db(PHOTOS_FILE)
for job in JOBS.values():
    if job.get("status") in ("queued", "working", "saving"):
        job["status"] = "failed"
        job["error"] = "The server restarted during generation. Saved scenes may be available."


def atomic_save(path: Path, obj: dict):
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def save_jobs():
    """Caller must hold LOCK."""
    jobs = sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)
    for old in jobs[MAX_HISTORY:]:
        JOBS.pop(old["id"], None)
    atomic_save(JOBS_FILE, JOBS)


def update_job(jid: str, **changes):
    with LOCK:
        job = JOBS.get(jid)
        if job is not None:
            job.update(changes)
            job["updated_at"] = timestamp()
            save_jobs()


def fal_request(url: str, *, payload: dict | None = None) -> dict:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "queue.fal.run":
        raise ValueError("Unrecognized video-generation queue URL")
    headers = {"Authorization": f"Key {FAL_KEY}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            obj = json.load(resp)
        if not isinstance(obj, dict):
            raise RuntimeError("Unexpected response from the video provider")
        return obj
    except urllib.error.HTTPError as exc:
        detail = exc.read(4000).decode("utf-8", errors="replace")
        try:
            parsed_detail = json.loads(detail)
            message = parsed_detail.get("detail") or parsed_detail.get("message") or parsed_detail.get("error") or detail
            if not isinstance(message, str):
                message = json.dumps(message)
        except Exception:
            message = detail
        raise RuntimeError(f"Video provider error {exc.code}: {str(message)[:400]}") from exc


def validate_media_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "fal.media" or host.endswith(".fal.media") or host == "storage.googleapis.com"
    )


def download_generated_video(url: str, destination: Path):
    if not validate_media_url(url):
        raise RuntimeError("The provider returned an unsupported video URL")
    request = urllib.request.Request(url, headers={"User-Agent": "OneHitWonder/2.0"})
    staging = destination.with_suffix(".part")
    count = 0
    try:
        with urllib.request.urlopen(request, timeout=150) as upstream, staging.open("wb") as out:
            if not validate_media_url(upstream.url):
                raise RuntimeError("Unsupported video redirect")
            while True:
                chunk = upstream.read(1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_VIDEO_BYTES:
                    raise RuntimeError("Generated scene exceeded the video size limit")
                out.write(chunk)
        if count < 100:
            raise RuntimeError("Generated video was unexpectedly empty")
        staging.replace(destination)
    finally:
        staging.unlink(missing_ok=True)


def photo_data_uri(pid: str) -> str:
    with LOCK:
        photo = PHOTO_LIBRARY.get(pid)
        if not photo:
            raise RuntimeError("Reference photo is missing. Re-upload it and retry.")
        path = PHOTOS / f"{pid}.{photo['extension']}"
        kind = photo["mime"]
    if not path.is_file():
        raise RuntimeError("A reference photo was lost after server restart. Re-upload it.")
    raw = path.read_bytes()
    if len(raw) > MAX_PHOTO_BYTES:
        raise RuntimeError("Reference photo is too large")
    return f"data:{kind};base64,{base64.b64encode(raw).decode('ascii')}"


def render_one(prompt: str, ratio: str, quality: str, duration: int, photo_ids: list[str], destination: Path, progress):
    request_data: dict = {"prompt": prompt, "aspect_ratio": ratio, "resolution": quality, "duration": duration}
    if photo_ids:
        # A single image in clip mode is animated as the opening frame; multiple
        # cast images are used as references for character/wardrobe consistency.
        model = IMAGE_MODEL if len(photo_ids) == 1 else REFERENCE_MODEL
        urls = [photo_data_uri(pid) for pid in photo_ids]
        if len(urls) == 1:
            request_data["image_url"] = urls[0]
        else:
            request_data["image_urls"] = urls
            request_data["prompt"] = (
                "Use the uploaded character reference images in order (<IMAGE_REF_0>, <IMAGE_REF_1>, etc.). "
                "Keep recognizable face and wardrobe continuity when feasible. " + prompt
            )[:2500]
    else:
        model = TEXT_MODEL
    progress("Submitting scene to the AI video engine…")
    result = fal_request(f"https://queue.fal.run/{model}", payload=request_data)
    request_id = result.get("request_id")
    status_url, response_url = result.get("status_url"), result.get("response_url")
    if not request_id or not status_url or not response_url:
        raise RuntimeError("Video provider did not supply a valid render request")
    progress("Waiting for the video engine…")
    for attempt in range(180):
        time.sleep(5)
        status_info = fal_request(status_url)
        if status_info.get("error"):
            raise RuntimeError(str(status_info["error"])[:400])
        if status_info.get("status") == "COMPLETED":
            break
        if attempt % 3 == 0:
            progress("In queue…" if status_info.get("status") == "IN_QUEUE" else "Rendering motion and dialogue…")
    else:
        raise RuntimeError("Video generation timed out. Check provider dashboard before retrying to avoid duplicate charges.")
    response = fal_request(response_url)
    if response.get("error"):
        raise RuntimeError(str(response["error"])[:400])
    media = response.get("video") or response.get("output", {}).get("video")
    video_url = media.get("url") if isinstance(media, dict) else None
    if not video_url:
        raise RuntimeError("Provider completed without an MP4 video")
    progress("Saving finished scene…")
    download_generated_video(video_url, destination)
    return request_id


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError("Movie assembly needs FFmpeg. Install imageio-ffmpeg on your host.") from exc


def assemble_movie(scene_paths: list[Path], destination: Path):
    """Re-encode scene clips to a shareable MP4 with a consistent video format."""
    if not scene_paths or any(not p.is_file() for p in scene_paths):
        raise RuntimeError("All scenes must be rendered before assembly")
    manifest = VIDEOS / f"concat-{destination.stem}.txt"
    # All paths are UUID-derived, not user-supplied.
    manifest.write_text("".join(f"file '{p.resolve()}'\n" for p in scene_paths), encoding="utf-8")
    staging = destination.with_suffix(".part.mp4")
    cmd = [ffmpeg_path(), "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(manifest),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(staging)]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
        if run.returncode != 0:
            raise RuntimeError(f"Movie assembly failed: {run.stderr[-500:]}")
        if staging.stat().st_size < 200:
            raise RuntimeError("Movie assembly produced an empty file")
        staging.replace(destination)
    finally:
        manifest.unlink(missing_ok=True)
        staging.unlink(missing_ok=True)


def build_scene_prompt(job: dict, scene: str, number: int) -> str:
    cast = ("Include recurring lead characters based on the supplied photo references. "
            "Keep recognizable faces and clothing as consistently as possible. ") if job["photo_ids"] else ""
    shot = (
        f"A self-contained scene from a FICTIONAL dramatic movie titled '{job['title']}'. "
        f"Genre: {job['genre']}. Look: {job['tone']}. "
        f"Overall story: {job['plot']}. Scene {number + 1} of {job['scene_count']}: {scene}. "
        f"{cast}Natural human expressions and grounded street-location details, immersive dialogue and ambient audio, "
        "realistic professional cinematography, dynamic camera movement, dramatic lighting, believable physical actions. "
        "One continuous shot, cinematic film realism, no subtitle overlays, no watermarks."
    )
    return shot[:2500]


def generate_job(jid: str):
    with LOCK:
        job = dict(JOBS.get(jid) or {})
    if not job:
        return
    try:
        update_job(jid, status="working")
        if job["kind"] == "clip":
            def progress(message):
                update_job(jid, progress=message)
            render_one(job["prompt"], job["aspect_ratio"], job["resolution"], job["duration"],
                       job.get("photo_ids", []), VIDEOS / f"{jid}.mp4", progress)
        else:
            completed = []
            for number, shot in enumerate(job["scenes"]):
                prefix = f"Scene {number + 1}/{job['scene_count']}: "
                def progress(message, head=prefix):
                    update_job(jid, progress=head + message, current_scene=number + 1)
                movie_prompt = build_scene_prompt(job, shot, number)
                file = VIDEOS / f"{jid}-scene-{number + 1}.mp4"
                render_one(movie_prompt, job["aspect_ratio"], job["resolution"], job["scene_duration"],
                           job["photo_ids"], file, progress)
                completed.append(f"/api/video/{jid}/scene/{number + 1}")
                update_job(jid, completed_scenes=list(completed), progress=f"{len(completed)} scenes finished")
            update_job(jid, status="saving", progress="Editing scenes into one movie MP4…")
            paths = [VIDEOS / f"{jid}-scene-{n}.mp4" for n in range(1, len(job["scenes"]) + 1)]
            assemble_movie(paths, VIDEOS / f"{jid}.mp4")
        update_job(jid, status="completed", progress="Your movie is ready!" if job["kind"] == "movie" else "Your clip is ready!",
                   video_url=f"/api/video/{jid}")
    except Exception as exc:
        logging.exception("Generation failed for %s", jid)
        update_job(jid, status="failed", progress="Unable to finish", error=str(exc)[:500])
        if BUSINESS_MODE and job.get("credits_used", 0):
            business.refund_render(job["user_id"], jid, job["credits_used"])


def identify_image(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return ("jpg", "image/jpeg")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("png", "image/png")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("webp", "image/webp")
    return None


def validated_photo_ids(value, user_id=None) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_PHOTOS_PER_JOB:
        raise ValueError("Select up to three cast photos")
    if len(set(value)) != len(value) or any(not isinstance(pid, str) or not re.fullmatch(r"[0-9a-f-]{36}", pid) for pid in value):
        raise ValueError("Invalid cast photo selection")
    with LOCK:
        if any(pid not in PHOTO_LIBRARY or (user_id and PHOTO_LIBRARY[pid].get("user_id") != user_id) for pid in value):
            raise ValueError("One or more cast photos are no longer available")
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "OneHitWonder/2.0"

    def respond(self, status: int, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _auth_required(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="One Hit Wonder Studio"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def authed(self) -> bool:
        if BUSINESS_MODE:
            self.user = business.from_cookie(self.headers.get("Cookie", ""))
            if not self.user:
                self.respond(401, {"error": "Please sign in to your One Hit Wonder account.", "code": "LOGIN_REQUIRED"})
                return False
            return True
        if not APP_PASSWORD:
            return True
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Basic "):
            self._auth_required()
            return False
        try:
            raw = base64.b64decode(auth.split(" ", 1)[1], validate=True).decode("utf-8")
            password = raw.split(":", 1)[1]
        except Exception:
            self._auth_required()
            return False
        if not secrets.compare_digest(password, APP_PASSWORD):
            self._auth_required()
            return False
        return True

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 32768:
                raise ValueError("Request is too large or empty")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("Invalid request")
            return value
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid request data") from exc

    def stream_file(self, file: Path, kind: str, *, download: bool = False):
        size = file.stat().st_size
        range_header = self.headers.get("Range", "")
        start, end, status = 0, size - 1, 200
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or (not match.group(1) and not match.group(2)):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            a, b = match.groups()
            if a:
                start = int(a)
                end = int(b) if b else size - 1
            else:
                start = max(0, size - int(b))
            if start >= size or start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            end, status = min(end, size - 1), 206
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "private, max-age=60")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="one-hit-wonder-{file.stem[:45]}.mp4"')
        self.end_headers()
        try:
            with file.open("rb") as inp:
                inp.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = inp.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/healthz":
            return self.respond(200, {"ok": True})
        if BUSINESS_MODE:
            if path == "/api/pricing":
                return self.respond(200, business.prices())
            if path == "/api/auth/me":
                user = business.from_cookie(self.headers.get("Cookie", ""))
                return self.respond(200, {"user": user})
            if path.startswith("/api/") and not self.authed():
                return
        elif not self.authed():
            return
        if BUSINESS_MODE and path == "/api/account/summary":
            with business.connect() as db:
                credits = [dict(x) for x in db.execute("SELECT amount,reason,created_at FROM ledger WHERE user_id=? ORDER BY created_at DESC LIMIT 40", (self.user["id"],))]
            return self.respond(200, {"user": self.user, "ledger": credits})
        if BUSINESS_MODE and path == "/api/admin/stats":
            if self.user["role"] != "owner":
                return self.respond(403, {"error": "Owner account required"})
            with LOCK:
                jobs = list(JOBS.values())
            return self.respond(200, business.admin_stats(jobs))
        if BUSINESS_MODE and path == "/api/admin/users":
            if self.user["role"] != "owner":
                return self.respond(403, {"error": "Owner account required"})
            return self.respond(200, {"users":business.admin_users()})
        if path == "/api/config":
            return self.respond(200, {"ready": bool(FAL_KEY), "engine": "Gemini Omni Flash 1.1",
                                      "rates": RATES, "max_running": MAX_RUNNING,
                                      "photo_mode": True, "movie_mode": True, "max_photos": MAX_PHOTOS_PER_JOB,
                                      "max_scenes": MAX_SCENES, "movie_assembly": True,
                                      "business_mode": BUSINESS_MODE, "credit_pricing": True})
        if path == "/api/photos":
            with LOCK:
                photos = sorted((p for p in PHOTO_LIBRARY.values() if not BUSINESS_MODE or p.get("user_id") == self.user["id"]), key=lambda p: p["created_at"], reverse=True)
            return self.respond(200, {"photos": photos})
        photo_match = re.fullmatch(r"/api/photos/([0-9a-f-]{36})", path)
        if photo_match:
            pid = photo_match.group(1)
            with LOCK:
                photo = PHOTO_LIBRARY.get(pid)
            if not photo or (BUSINESS_MODE and photo.get("user_id") != self.user["id"]):
                return self.respond(404, {"error": "Photo not found"})
            file = PHOTOS / f"{pid}.{photo['extension']}"
            if not file.is_file():
                return self.respond(404, {"error": "Photo file missing"})
            return self.stream_file(file, photo["mime"])
        if path == "/api/jobs":
            with LOCK:
                jobs = sorted((j for j in JOBS.values() if not BUSINESS_MODE or j.get("user_id") == self.user["id"]), key=lambda j: j["created_at"], reverse=True)[:24]
            return self.respond(200, {"jobs": jobs})
        job_match = re.fullmatch(r"/api/jobs/([0-9a-f-]{36})", path)
        if job_match:
            with LOCK:
                job = JOBS.get(job_match.group(1))
            return self.respond(200, {"job": job}) if job and (not BUSINESS_MODE or job.get("user_id") == self.user["id"]) else self.respond(404, {"error": "Video not found"})
        video_match = re.fullmatch(r"/api/video/([0-9a-f-]{36})(?:/scene/([1-8]))?", path)
        if video_match:
            jid, scene = video_match.groups()
            with LOCK:
                job = JOBS.get(jid)
            if not job or (BUSINESS_MODE and job.get("user_id") != self.user["id"]):
                return self.respond(404, {"error": "Video not found"})
            if scene:
                if f"/api/video/{jid}/scene/{scene}" not in job.get("completed_scenes", []):
                    return self.respond(404, {"error": "Scene not ready"})
                file = VIDEOS / f"{jid}-scene-{scene}.mp4"
            else:
                if job["status"] != "completed":
                    return self.respond(404, {"error": "Video not ready"})
                file = VIDEOS / f"{jid}.mp4"
            if not file.is_file():
                return self.respond(404, {"error": "Video is unavailable; host storage may have reset"})
            download = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("download") == ["1"]
            return self.stream_file(file, "video/mp4", download=download)
        if BUSINESS_MODE:
            path = {"/": "/index.html", "/studio": "/studio.html", "/pricing": "/pricing.html",
                    "/dashboard": "/dashboard.html", "/admin": "/admin.html", "/login": "/login.html"}.get(path, path)
        elif path == "/":
            path = "/studio.html"
        pathname = (PUBLIC / path.lstrip("/")).resolve()
        if PUBLIC.resolve() not in pathname.parents or not pathname.is_file():
            return self.respond(404, {"error": "Not found"})
        kind = mimetypes.guess_type(pathname.name)[0] or "application/octet-stream"
        if pathname.suffix == ".js":
            kind = "text/javascript"
        content = pathname.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache" if pathname.suffix in (".js", ".html", ".css") else "public, max-age=3600")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_DELETE(self):
        if not self.authed():
            return
        match = re.fullmatch(r"/api/photos/([0-9a-f-]{36})", urllib.parse.urlsplit(self.path).path)
        if not match:
            return self.respond(404, {"error": "Not found"})
        pid = match.group(1)
        with LOCK:
            existing = PHOTO_LIBRARY.get(pid)
            photo = PHOTO_LIBRARY.pop(pid, None) if existing and (not BUSINESS_MODE or existing.get("user_id") == self.user["id"]) else None
            if photo:
                atomic_save(PHOTOS_FILE, PHOTO_LIBRARY)
        if photo:
            (PHOTOS / f"{pid}.{photo['extension']}").unlink(missing_ok=True)
        return self.respond(200, {"deleted": bool(photo)})

    def upload_photo(self):
        if self.headers.get("X-Photo-Consent") != "yes":
            return self.respond(400, {"error": "Confirm you own or have permission to use this person's photo"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length <= 40 or length > MAX_PHOTO_BYTES:
            return self.respond(413, {"error": "Each photo must be under 3 MB. Try a smaller image."})
        data = self.rfile.read(length)
        found = identify_image(data)
        if not found:
            return self.respond(415, {"error": "Upload a JPG, PNG, or WebP image. iPhone photos will be converted to JPG."})
        ext, mime = found
        try:
            label = urllib.parse.unquote(self.headers.get("X-Photo-Name", "My character photo"))[:80]
        except Exception:
            label = "My character photo"
        label = re.sub(r"[\x00-\x1f\x7f]", "", label).strip() or "My character photo"
        with LOCK:
            if sum(not BUSINESS_MODE or p.get("user_id") == self.user["id"] for p in PHOTO_LIBRARY.values()) >= MAX_PHOTO_LIBRARY:
                return self.respond(429, {"error": "Photo library is full. Delete an older photo first."})
            pid = str(uuid4())
            destination = PHOTOS / f"{pid}.{ext}"
            destination.write_bytes(data)
            photo = {"id": pid, "label": label, "extension": ext, "mime": mime, "bytes": len(data),
                     "user_id": self.user["id"] if BUSINESS_MODE else None,
                     "created_at": timestamp(), "url": f"/api/photos/{pid}"}
            PHOTO_LIBRARY[pid] = photo
            atomic_save(PHOTOS_FILE, PHOTO_LIBRARY)
        return self.respond(201, {"photo": photo})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if BUSINESS_MODE and path == "/api/stripe/webhook":
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 100000:
                    raise ValueError("Invalid webhook length")
                payload = self.rfile.read(size)
                return self.respond(200, business.handle_webhook(payload,self.headers.get("Stripe-Signature", "")))
            except (ValueError, TypeError, KeyError) as exc:
                return self.respond(400, {"error":str(exc)[:140]})
        if BUSINESS_MODE and path in ("/api/auth/register", "/api/auth/login"):
            try:
                body = self.read_json()
                if path.endswith("register"):
                    business.create_user(body.get("email"),body.get("name"),body.get("password"),body.get("owner_code",""))
                token, user = business.login(body.get("email"),body.get("password"))
                return self.respond(200, {"user":user}, {"Set-Cookie":business.cookie(token)})
            except (ValueError,TypeError) as exc:
                return self.respond(400,{"error":str(exc)[:200]})
        if BUSINESS_MODE and path == "/api/auth/logout":
            business.logout(self.headers.get("Cookie", ""))
            return self.respond(200,{"ok":True},{"Set-Cookie":business.cookie("",clear=True)})
        if not self.authed():
            return
        if BUSINESS_MODE and path == "/api/billing/checkout":
            try:
                body=self.read_json()
                return self.respond(200,{"url":business.checkout(self.user["id"],body.get("sku"))})
            except (ValueError,TypeError) as exc:
                return self.respond(400,{"error":str(exc)[:220]})
        if BUSINESS_MODE and path == "/api/admin/grant":
            if self.user["role"] != "owner":return self.respond(403,{"error":"Owner account required"})
            try:
                body=self.read_json()
                business.grant_credits(self.user["id"],body.get("user_id"),int(body.get("amount",0)))
                return self.respond(200,{"ok":True})
            except (ValueError,TypeError) as exc:
                return self.respond(400,{"error":str(exc)[:150]})
        if path == "/api/photos":
            return self.upload_photo()
        if path not in ("/api/jobs", "/api/movies"):
            return self.respond(404, {"error": "Not found"})
        if not FAL_KEY:
            return self.respond(503, {"error": "Connect your fal.ai API key to activate real AI video generation.",
                                      "code": "SETUP_REQUIRED"})
        try:
            body = self.read_json()
            ratio = body.get("aspect_ratio", "16:9")
            quality = body.get("resolution", "720p")
            duration = body.get("duration", 8)
            if ratio not in ("9:16", "16:9") or quality not in RATES or type(duration) is not int or not 3 <= duration <= 10:
                raise ValueError("Choose a valid format, quality and duration")
            photo_ids = validated_photo_ids(body.get("photo_ids", []), self.user["id"] if BUSINESS_MODE else None)
            if photo_ids and body.get("photo_consent") is not True:
                raise ValueError("Confirm you have permission to use the photos")
            if path == "/api/jobs":
                prompt = body.get("prompt")
                if not isinstance(prompt, str) or not 6 <= len(prompt.strip()) <= 2500:
                    raise ValueError("Describe the scene in 6–2,500 characters")
                kind = "clip"
                record = {"prompt": prompt.strip(), "duration": duration}
                cost = RATES[quality] * duration
            else:
                title, plot = body.get("title"), body.get("plot")
                genre, tone = body.get("genre"), body.get("tone")
                scenes = body.get("scenes")
                if not isinstance(title, str) or not 2 <= len(title.strip()) <= 85:
                    raise ValueError("Give your movie a title (2–85 characters)")
                if not isinstance(plot, str) or not 10 <= len(plot.strip()) <= 1200:
                    raise ValueError("Describe your film's story (10–1,200 characters)")
                if genre not in GENRES or tone not in TONES:
                    raise ValueError("Choose a supported movie genre and visual tone")
                if not isinstance(scenes, list) or not 3 <= len(scenes) <= MAX_SCENES:
                    raise ValueError("Movies contain 3–8 editable scenes")
                if any(not isinstance(scene, str) or not 8 <= len(scene.strip()) <= 500 for scene in scenes):
                    raise ValueError("Describe each scene in 8–500 characters")
                if quality == "4k":
                    raise ValueError("Movie assembly supports up to 1080p. Change the resolution.")
                if body.get("acknowledge_cost") is not True:
                    raise ValueError("Confirm the estimated charges before rendering a multi-scene movie")
                kind = "movie"
                record = {"title": title.strip(), "plot": plot.strip(), "prompt": plot.strip(),
                          "genre": genre, "tone": tone, "scenes": [s.strip() for s in scenes],
                          "scene_count": len(scenes), "scene_duration": duration,
                          "duration": duration * len(scenes), "completed_scenes": [], "current_scene": 0}
                cost = RATES[quality] * duration * len(scenes)
            with LOCK:
                active = sum(j.get("status") in ("queued", "working", "saving") for j in JOBS.values())
                if active >= MAX_RUNNING:
                    return self.respond(429, {"error": "Two renders are in progress. Try again after one finishes."})
                jid = str(uuid4())
                job = {"id": jid, "kind": kind, "status": "queued", "created_at": timestamp(),
                       "updated_at": timestamp(), "aspect_ratio": ratio, "resolution": quality,
                       "photo_ids": photo_ids, "cost_estimate": round(cost, 2),
                       "progress": "Preparing your production…", "video_url": None, "error": None, **record}
                if BUSINESS_MODE:
                    credits = business.credit_quote(kind,quality,duration,len(photo_ids),len(record.get("scenes",[])))
                    charged = business.reserve_credits(self.user["id"],jid,credits,self.user["role"]=="owner")
                    job["user_id"] = self.user["id"]
                    job["credits_used"] = charged
                    job["credit_quote"] = credits
                JOBS[jid] = job
                save_jobs()
            threading.Thread(target=generate_job, args=(jid,), daemon=True, name=f"movie-{jid[:8]}").start()
            return self.respond(202, {"job": job})
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": str(exc)[:350]})


if __name__ == "__main__":
    if not FAL_KEY:
        logging.warning("FAL_KEY missing: preview and photo library work, paid AI rendering unavailable")
    if HOST == "0.0.0.0" and not APP_PASSWORD and not BUSINESS_MODE:
        logging.warning("Set APP_PASSWORD before public deployment; photos are private user data")
    if BUSINESS_MODE and not business.OWNER_INVITE_CODE:
        logging.warning("OWNER_INVITE_CODE is missing: owner account cannot be created")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    logging.info("One Hit Wonder Street Cinema running on http://%s:%s", HOST, PORT)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()
