# ONE HIT WONDER by IconEnt — Street Cinema Business Pilot

A mobile-first AI video creator plus business website, owner dashboard, customer accounts, credit tracking, and Stripe checkout integration. Built for realistic **fictional** neighborhood dramas, action films, music videos, romance and other original short films.

## Site pages

- `/` — public landing page and working **free** editable storyboard preview
- `/studio` — your existing photo-to-video, scene director, cast library and video downloads (login required)
- `/pricing` — credit packs and monthly plans; payment buttons remain disabled until verified Stripe is connected
- `/login` — customer signup and sign-in; private owner invitation
- `/dashboard` — user credit balance, job history and ledger
- `/admin` — owner metrics, users and promotional credit grants

## Owner / customer billing

Owners get **unlimited internal app credits**, not free third-party compute. Customers are charged defined video credits with atomic reservation, and failed jobs receive an idempotent credit refund. Stripe purchase credits are issued exclusively on verified webhooks; no browser-only purchases or fabricated balances.

## Fast local startup

```bash
python3 -m pip install -r requirements.txt
export BUSINESS_MODE=1 COOKIE_SECURE=0 SIGNUPS_ENABLED=1
export OWNER_EMAIL='owner@example.com'
export OWNER_INVITE_CODE='choose-a-very-long-secret-code-you-control'
python3 server.py
```

Visit `http://127.0.0.1:8080/` and explore the free storyboard. Visit `/login` to create a customer account, or use the owner email + invitation code for the one owner account. Local storage uses SQLite. `FAL_KEY` is optional; without it real video renders remain disabled, and the free storyboard still works.

For public hosting, set `HOST=0.0.0.0`, `BUSINESS_MODE=1`, `COOKIE_SECURE=1`, `SIGNUPS_ENABLED=0`, `CHECKOUT_ENABLED=0`, `OWNER_EMAIL` and `OWNER_INVITE_CODE`. Set up `PUBLIC_BASE_URL` after the service exists. `APP_PASSWORD` is only used in the old single-user mode, not in business mode.

## Deploy to Render

Code repo: `marcushargrove916-bot/IconEnt`. Python build: `pip install -r requirements.txt`. Start: `python3 server.py`. The `render.yaml` file specifies a private owner pilot, but requires environment setup. Render previously returned HTTP 402 on service creation, requiring billing information even on free instances. No guaranteed live domain exists until Render confirms a successful deployment.

**Do not enable public payments yet.** This is a locally tested pilot, **not a production-ready public billing system**. Render Free storage is ephemeral. Move the SQLite database and customer photos/videos to durable managed storage, implement email verification/password recovery and protection against abuse, then connect Stripe and turn on checkout. See the documentation below.

## Docs

- [Business & launch plan](docs/BUSINESS_PLAN.md)
- [Feature & technical specification](docs/PRODUCT_SPEC.md)
- [Launch checklist](docs/LAUNCH_CHECKLIST.md)

## External video engine

The current app integrates with fal.ai Gemini Omni Flash 1.1 text-to-video, image-to-video, and multiple-reference modes. Requires a funded `FAL_KEY` for real videos. Provider model restrictions, output quality limitations and prices apply. A 3–8 scene production uses several separately billed generations. Keep photos limited to images you own or have permission to use. There is no bypass of provider safety requirements.
