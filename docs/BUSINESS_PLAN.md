# One Hit Wonder by IconEnt — Business & Launch Plan

**Version:** November 2026 · **Owner:** IconEnt · **Product:** One Hit Wonder / Street Cinema

## Executive summary

One Hit Wonder is a mobile-first website where creators upload photographs they have permission to use, develop film scenes, and produce cinematic AI clips or short multi-scene movies. The initial market is independent artists, creators, clothing brands, music video producers and fiction storytellers. The product should be presented as original creative technology; it is not affiliated with Sora or any AI video provider.

## What is included in this release

- Landing page with working **free browser storyboard** (no charge, no AI footage)
- Owner and customer registration/login with hashed passwords and session cookies
- Owner dashboard showing users, credit grant controls, sales from verified Stripe webhooks, jobs and estimated rendering costs
- Customer dashboard showing credits, plan, video history and credit transactions
- Pricing page showing four one-time credit packs and three monthly subscriptions; payment actions remain disabled until securely configured
- Private photo library and Street Cinema creator from the prior application
- Backend credit reservation/refund and photo/video isolation across accounts
- Stripe Checkout and verified webhook code, dormant until live keys/prices and durable storage are installed

**Not yet production-ready:** public customer billing, durable hosted storage, email verification, recovery, scalable job queue, moderation operational plan and paid video-generation testing. Hosting has not been confirmed live and Render previously required billing verification.

## Market positioning

**Core message:** Turn your pictures and your stories into short cinematic movies.

Primary user groups: independent rappers and music creators; aspiring short-film directors; social-media creators; streetwear and product brands; small creative teams. Film genres include urban drama, neighborhood family stories, romance, music films and fictional action. Video provider policies apply; avoid promises of unrestricted content or perfect facial likeness.

## Pricing hypothesis

| Product | Customer price | Included credits | Effective price per credit |
|---|---:|---:|---:|
| Starter Pack | $9.99 once | 10 | $1.00 |
| Creator Pack | $24.99 once | 30 | $0.83 |
| Director Pack | $49.99 once | 70 | $0.71 |
| Studio Pack | $99.99 once | 160 | $0.62 |
| Basic | $14.99/month | 15 per paid cycle | $1.00 |
| Pro | $39.99/month | 50 per paid cycle | $0.80 |
| Studio | $99.99/month | 150 per paid cycle | $0.67 |

These are **proposed prices**, not activated customer offerings. Validate actual provider pricing, refund costs, platform processing fees, model output quality and conversion before public activation. Recurring credits are granted on verified paid invoices, not merely customer clicks.

Video credit estimates in current code: basic text clip = 2; photo clip = 3; 3-scene movie = 8; 5 scenes = 12; 8 scenes = 18. Premium quality, long duration and photo references use more credits. Owner credits are internally unlimited, **not** free AI compute.

## Unit economics — illustrative, not forecasts

For example, an 8-second 720p AI scene at an estimated $0.10/second incurs $0.80 in model fees *before* storage, processing, failed renders, payment fees, refunds or customer support. A 5-scene movie could consume about $4.00 of model fees at that rate. Provider rates vary and can change. The app reports estimates but does not yet reconcile actual invoices.

Revenue illustration only: 50 Basic accounts ($749.50), 25 Pro accounts ($999.75), ten Director packs ($499.90) = **$2,249.15 gross sales**, before all costs. This is not a revenue forecast or profit promise.

## Launch phases and decision gates

**Phase 1 — private owner pilot:** secure owner invitation, access site, storyboard and cast upload, confirm privacy, create paid test clips, confirm provider costs. Limit provider spend with an account-side budget.

**Phase 2 — controlled beta:** durable PostgreSQL and private object storage; customer email verification and password recovery; signed-in upload protections, queue and spend limits; Stripe in test mode including refunds/failed invoices; legal/privacy review. Invite a small user group and monitor quality/cost.

**Phase 3 — public launch:** enable signups and production Stripe only after go/no-go checks. Publish support contacts, terms, privacy, refunds, and use policies; roll out IconEnt social-media demos, creator partnerships and conversion tracking.

## Marketing starter campaign

- Hook: **“Your pictures. Your characters. Your short movie.”**
- Showcase three clips: realistic neighborhood drama, music video performance and streetwear commercial.
- Emphasize **free storyboard preview**, with clear paid-video disclosure.
- Make 15–30-second vertical promotional clips; always disclose AI-generated content where required.
- Invite a limited group of real filmmakers and artists to collect feedback rather than buying traffic before reliability is proven.

## Risks and mitigations

- **Provider failures or rejected prompts:** show errors and predictable refund rules; do not guarantee unrestricted outputs.
- **Cost overruns:** per-account and global generation limits, budget caps, and pre-quote credits.
- **Identity and likeness misuse:** user consent acknowledgment, reporting/removal process, no deceptive impersonation.
- **Data loss:** persistent SQL/object storage with backup and retention policy before public billing.
- **Unauthorized purchases:** verified Stripe webhooks, idempotent credit grants and customer receipts.
- **Weak output consistency:** clearly disclose AI variations and allow scene editing/re-renders.

## Success measures

Landing-to-storyboard use, storyboard-to-registration conversion, paid conversion, average credits per video, cost per completed second, failed-render rates, refund rate, creator retention, and gross margin after provider and payment fees.
