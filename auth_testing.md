# Auth Testing Playbook (PAPERBRAIN)

PAPERBRAIN supports THREE auth flows that all yield a JWT Bearer token:
1. **Email + password signup / login** (JWT, bcrypt) — `POST /api/auth/signup`, `POST /api/auth/login`
2. **Emergent-managed Google Auth** — `POST /api/auth/google/session` with `{ session_id }`
3. **Password reset via Resend email** — `POST /api/auth/forgot-password` → `POST /api/auth/reset-password`

All authenticated endpoints accept `Authorization: Bearer <jwt>` header.

## Existing test user
- **Email**: test@test.com
- **Password**: testpass123

## Google OAuth test flow (frontend)
1. Click "Continue with Google" on `/auth` → redirects to `https://auth.agent.com/?redirect=<origin>/auth/callback`
2. Complete Google auth → browser returns to `/auth/callback#session_id=<xxx>`
3. Frontend `AuthCallback` component extracts session_id, POSTs to `/api/auth/google/session`
4. Backend calls Emergent `/session-data`, creates/links user by email, returns our JWT
5. Frontend stores JWT and navigates to `/library`

## Password reset test flow
1. `POST /api/auth/forgot-password { email }` → always returns 200 (no email enumeration)
2. If user exists, an email is sent (Resend). Placeholder mode logs to backend log.
3. User clicks link → lands on `/reset-password?token=<jwt>` → sets new password → `POST /api/auth/reset-password { token, new_password }`

## Email verification
1. On signup, an email is sent with `/verify-email?token=<jwt>`
2. User clicks → frontend calls `POST /api/auth/verify-email { token }` → user record marked `email_verified: true`

## Change password (authenticated)
- `POST /api/auth/change-password { current_password, new_password }` — requires Bearer JWT

## Notes
- RESEND_API_KEY is a PLACEHOLDER (`re_placeholder_api_key`). In this mode, emails are NOT sent — they are logged to backend logs as `[MOCK EMAIL - no RESEND_API_KEY]`. This is expected and lets us test the full flow without paying for email. Replace with a real key from https://resend.com to enable real delivery.
- Emergent Google Auth requires no keys.
