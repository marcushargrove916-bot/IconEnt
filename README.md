# IconEnt · One Hit Wonder AI

Mobile-first AI text-to-video web app hosted on Render. Run with Python 3.10+.

The application is packaged as `one-hit-wonder.tar.gz`. The Render build command extracts it with `tar -xzf one-hit-wonder.tar.gz`, and the start command is `python3 server.py`.

Set `APP_PASSWORD` and `HOST=0.0.0.0` in Render; add secret `FAL_KEY` to activate paid AI renders. Never commit secret keys.

Render Free storage is ephemeral; downloaded video files may disappear when the service restarts.
