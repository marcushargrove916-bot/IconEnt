# One Hit Wonder — Launch Checklist

- [x] Brand and landing page
- [x] Free browser storyboard preview
- [x] Photo-to-video and short scene-based film engine
- [x] Customer registration/login and owner invitation mechanism
- [x] Owner management dashboard and credit grants
- [x] Customer dashboard and history
- [x] Proposed credit packs and memberships
- [x] Server-enforced customer credit deductions and failure refunds
- [x] Stripe Checkout/webhook code gated off until ready
- [x] Local integration tests for accounts, isolation, video assembly and credits
- [ ] Render live URL (Render may require card even on Free plan)
- [ ] `OWNER_EMAIL` and `OWNER_INVITE_CODE` set privately in Render
- [ ] Actual owner account registered at `/login`
- [ ] fal.ai funded API key (required only for real video generation)
- [ ] Postgres and private object storage (required before public billing)
- [ ] Email verification, password recovery and owner 2FA
- [ ] Full rate limiting, global spend budget and background task queue
- [ ] Stripe test/live keys, webhook and seven Price IDs
- [ ] Test payment, cancel, recurring invoice, refund and dispute flows
- [ ] Legal privacy/terms/refund policies and abuse reporting
- [ ] Public signups explicitly enabled after pilot testing
- [ ] Customer-ready launch review and legal/financial approval

**Important:** Being the app owner waives the app's internal credit charge, **not** the third-party AI provider's computing fees. The free storyboard is not the same as generated video footage.
