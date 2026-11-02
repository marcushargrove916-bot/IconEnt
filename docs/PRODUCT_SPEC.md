# One Hit Wonder by IconEnt — Technical & Feature Specification

## Routes

| URL | Capability | Access |
|---|---|---|
| `/` | Branded home page, free editable in-browser storyboard | Public |
| `/pricing` | Credit packs and membership cards; Checkout only when enabled | Public; purchase needs login |
| `/login` | Sign in, register and optional owner invitation | Public |
| `/studio` | Photo library, one-shot AI video, 3–8 scene Street Cinema | Signed-in |
| `/dashboard` | Credit balance, current plan, history and ledger | Signed-in |
| `/admin` | User metrics, cost estimates and customer credit grants | Owner only |

## Functional API

- `GET /healthz` — liveness check.
- `GET /api/pricing` — server-priced plans and checkout enabled/disabled flags.
- `POST /api/auth/register` — password-based signup; owner requires matching configured email + long invitation.
- `POST /api/auth/login` — secure cookie session; password hashes use PBKDF2-SHA256.
- `GET /api/auth/me`, `POST /api/auth/logout` — account session.
- `GET /api/account/summary` — credit ledger and current user.
- `GET /api/photos`, `POST /api/photos`, `DELETE /api/photos/{id}` — per-user photo library.
- `POST /api/jobs`, `POST /api/movies` — reserve customer credits and generate video; owner skips internal debit.
- `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/video/{id}` — per-user results.
- `POST /api/billing/checkout` — creates Stripe-hosted session from configured price ID.
- `POST /api/stripe/webhook` — validates Stripe signature, grants credits idempotently.
- `GET /api/admin/stats`, `GET /api/admin/users`, `POST /api/admin/grant` — owner only.

## Account and credit logic

Roles: `owner`, `customer`. Owner registration requires `OWNER_EMAIL` and `OWNER_INVITE_CODE` (minimum 20 characters) and only one owner account may be created. Customer accounts have actual nonnegative integer credit balances. Rendering uses atomic SQLite decrements to prevent overspend; failed whole-job render attempts trigger at most one refund. Stripe events are signature-verified and deduplicated.

## Video workflow

Upload up to 24 JPG/PNG/WebP photos per account, selecting at most three for a generation. Prompt, scene style, duration, ratio and quality configure the external fal.ai model. Scenes are generated sequentially, saved privately and combined with FFmpeg into an MP4. Generation provider charges are external. The API may reject prompts, reference faces may vary and scene transitions are not perfectly consistent. Video scene limits are 3, 5, and 8 in the website UI.

## Security and scale limitations

This release is a **single-server pilot**. It uses SQLite and local media files, which are ephemeral on Render Free. Do not accept real paying customers on ephemeral storage. Before public billing, migrate to managed Postgres, private object storage, background worker queue, verified emails, password resets/2FA for owner, per-customer rate limits, spending caps, logged admin changes, backups, customer support, deletion flows and clear legal documents. The app does not bypass external providers' safety requirements.

## Environment and deployment

Use `BUSINESS_MODE=1`, `COOKIE_SECURE=1`, a long `OWNER_INVITE_CODE`, a private `OWNER_EMAIL`, `HOST=0.0.0.0`, and `PUBLIC_BASE_URL` after hosting. Set `SIGNUPS_ENABLED=0` and `CHECKOUT_ENABLED=0` for a private pilot. Configure `FAL_KEY` only if you choose to pay for actual AI generation. Connect Stripe live or test credentials and all price IDs only after durable storage is ready. Never put keys, passwords or people's uploaded photos into GitHub.

## Definition of done

**Completed and locally tested:** landing, storyboard preview, login/register, dashboard, owner grants, per-account isolation, credit reservation/refund, pricing, and dormant payment integration. **Blocked external dependencies:** hosting acceptance on Render, private owner bootstrap, funded AI provider, and live Stripe account. **Production launch:** not yet complete.
