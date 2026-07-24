# Test Credentials for Personal AI Knowledge Assistant

## Test User Account (email + password)
- **Email**: test@test.com
- **Password**: testpass123 (may have been changed during testing — use signup if login fails)
- **Name**: Test User

## Auth Flows Supported
1. Email + password (JWT, bcrypt) — `/api/auth/signup`, `/api/auth/login`
2. Google OAuth via Emergent-managed Auth — `/api/auth/google/session` (browser only)
3. Password reset via Resend email — `/api/auth/forgot-password` → `/api/auth/reset-password`
4. Email verification — `/api/auth/verify-email`

## Placeholder Keys (replace with real ones for live behavior)
- `RESEND_API_KEY=re_placeholder_api_key` — emails MOCKED to backend log
- `RAZORPAY_KEY_ID=rzp_test_placeholder` — Razorpay orders fail with "Authentication failed"
- Emergent Google OAuth: **no keys needed** (zero-config)

## LLM Integration
- `EMERGENT_LLM_KEY` (Universal Key) — Claude Sonnet 4.5 for RAG chat
- Local ChromaDB ONNX embeddings (all-MiniLM-L6-v2)

## Key Endpoints (all /api-prefixed)
- Auth: /auth/signup, /auth/login, /auth/me, /auth/forgot-password, /auth/reset-password, /auth/verify-email, /auth/resend-verification, /auth/send-verification, /auth/change-password, /auth/update-profile, /auth/google/session
- Documents: /documents/upload, /documents/url, /documents (GET, DELETE)
- Chat: /chat/stream (SSE), /conversations
- Billing: /billing/plans, /billing/status, /billing/create-order, /billing/verify-payment, /billing/webhook
