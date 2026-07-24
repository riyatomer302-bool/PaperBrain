# PAPERBRAIN — Personal AI Knowledge Assistant

## Original Problem Statement
A Personal AI Knowledge Assistant that ingests all your personal documents, emails, learning materials, and then provides conversational access to your entire knowledge base. Must include: vector database, RAG, privacy/security, seamless chat interface. Completely working, deploy-ready project.

## User Choices
- LLM: Claude Sonnet 4.5 via Emergent Universal LLM Key
- Vector DB: ChromaDB (local, per-user namespaces)
- Doc types: PDF, DOCX, TXT, MD, EML + URL scraping
- Auth: JWT-based custom (bcrypt hashed passwords)

## Architecture
- **Frontend**: React 19 + React Router 7, Tailwind, Shadcn UI, Phosphor Icons, SSE-based streaming
- **Backend**: FastAPI + Motor (MongoDB) for auth/messages/docs metadata + ChromaDB (persistent) for vectors
- **Embeddings**: ChromaDB DefaultEmbeddingFunction (ONNX all-MiniLM-L6-v2, 384-dim, local)
- **LLM**: Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) via emergentintegrations LlmChat.stream_message
- **Auth**: bcrypt + PyJWT (30-day tokens)

## Design
Swiss & High-Contrast dark theme, Cabinet Grotesk + IBM Plex Sans/Mono, monochrome + blue primary + green privacy accent. Tri-pane chat: history rail / transcript / citations panel.

## Implemented (2026-02-23)
- Landing page (hero + features + CTA)
- Auth page (signup/login, JWT)
- Library dashboard (upload PDF/DOCX/TXT/MD/EML, ingest URL, list, delete, stats)
- Chat page (streaming SSE, inline citations, history rail, citation panel, new/delete conversation)
- Backend: 12 API endpoints, all /api-prefixed
- Multi-tenant vector namespaces (per-user Chroma collections)
- 18/18 backend tests passed (auth, docs, RAG chat, user isolation, deletion)

### Added 2026-02-23 (Razorpay billing)
- Razorpay integration: /api/billing/plans, /status, /create-order, /verify-payment, /webhook
- Pricing page (/pricing) with Free + Pro ₹499/month cards
- Header "Upgrade" button → Razorpay Checkout modal → signature verification → 30-day Pro subscription
- MongoDB collections: payments, subscriptions, webhook_events
- Currently using placeholder Razorpay keys — user needs to replace with real rzp_test_* keys in /app/backend/.env
- 17/17 billing + regression tests passed

### Added 2026-02-23 (Auth extensions)
- Password reset via Resend email: /api/auth/forgot-password, /api/auth/reset-password (JWT purpose-tokens, 1h TTL)
- Email verification on signup: /api/auth/verify-email, /api/auth/resend-verification, /api/auth/send-verification (24h TTL tokens)
- Emergent-managed Google OAuth: /api/auth/google/session — auto-links to existing email, issues our JWT
- Change password (authenticated): /api/auth/change-password
- Update profile (authenticated): /api/auth/update-profile
- New frontend pages: /forgot-password, /reset-password, /verify-email, /auth/callback, /profile
- "Continue with Google" button + "Forgot password" link on Auth page
- Profile page with resend-verification, change-password, name editing
- Resend key is PLACEHOLDER — emails currently MOCKED to backend log. Replace RESEND_API_KEY in /app/backend/.env for real delivery
- 43/43 backend tests passed (26 new auth_ext + 17 billing regression)

### Added 2026-02-23 (Plan limits enforcement)
- Free tier caps: 10 documents, 200 vector chunks (across all docs), 50 chat messages / calendar month
- New endpoint `/api/billing/usage`: real-time usage + percent + limits
- Enforcement returns HTTP 402 with clear detail message
- Doc-record rollback if chunk-count would exceed cap
- Pro subscription bypasses all limits; expired Pro auto-reverts to Free (status flipped in DB)
- Library dashboard: usage bars (turn red at ≥80%) + upgrade banner at ≥70%
- Chat + upload UIs show sonner toast with "Upgrade" action on 402
- Messages now store `user_id` for accurate chat-count filtering (no cap on user's conversation count)
- 66/66 backend tests passed (23 plan limits + 26 auth_ext + 17 billing)

### Added 2026-02-23 (Rate limiting + billing history)
- In-memory sliding-window rate limiter (`rate_limit.py`), per-IP with X-Forwarded-For support
- POST /api/auth/login: 5/15min per IP; counter resets on successful login
- POST /api/auth/forgot-password: 3/hour per IP (check runs before DB lookup — no email enumeration)
- POST /api/auth/signup: 10/hour per IP
- HTTP 429 with `Retry-After` header (integer seconds)
- New endpoint /api/billing/payments — paginated (top 200) payment history, sorted by created_at desc, hides razorpay_signature and _id, adds plan_name + amount_inr
- Profile page now shows a "Billing history" section with paid/failed badges and Razorpay payment IDs
- 78/78 backend tests passed (12 new rate-limit + billing-history + 66 regression)

## Backlog (P1)
- Streaming stop button
- Per-document view with chunks preview
- Batch upload progress bar
- Dark/light mode toggle
- Export conversation as markdown
- API key management page (user-provided keys)

## Backlog (P2)
- OCR for scanned PDFs
- Recurring web page re-indexing
- Shareable conversation links
- Slack/Notion connectors
