# Add user authentication with JWT tokens

## Summary

Implements JWT-based authentication for the REST API, replacing the previous
session-cookie approach. Users can now sign up, log in, and access protected
endpoints using Bearer tokens. Refresh tokens are stored in HttpOnly cookies
for security.

## Motivation / Context

Resolves #142. The session-cookie auth was causing issues with our mobile app
and third-party API consumers who need stateless authentication. The team
decided to migrate to JWT during the Q1 planning (see RFC-2024-03).

## Key Changes

- **Auth module (`src/auth/`)**: New module with `AuthService`, `JwtStrategy`,
  and `RefreshTokenStrategy`. Tokens expire after 15 minutes; refresh tokens
  last 7 days.
- **User registration (`src/auth/register.ts`)**: Added email validation,
  password strength checks (zxcvbn), and duplicate-email handling with a
  clear error message.
- **Protected route guard (`src/middleware/auth-guard.ts`)**: Express middleware
  that verifies JWT tokens and attaches the decoded user to `req.user`.
  Returns 401 with a structured error if the token is invalid or expired.
- **Database migration (`migrations/004_add_refresh_tokens.sql`)**: New
  `refresh_tokens` table with user_id foreign key and expiry index.
- **Config updates (`src/config.ts`)**: Added `JWT_SECRET` and
  `JWT_REFRESH_SECRET` to the environment schema with validation.
- **Removed**: Deleted `src/middleware/session.ts` and the `express-session`
  dependency — no longer needed.

## Testing Notes

- Unit tests added for `AuthService` (token generation, validation, refresh
  flow) in `src/auth/__tests__/auth-service.test.ts`
- Integration tests for the full auth flow (register → login → access →
  refresh → logout) in `test/integration/auth.test.ts`
- Manual testing: Run `npm run dev`, then use the Postman collection in
  `docs/auth-api.postman.json` to exercise the endpoints
- The migration needs to be run: `npm run migrate`

## Breaking Changes

- **All authenticated endpoints now require Bearer token** instead of session
  cookies. Clients must update their auth headers from `Cookie: session=...`
  to `Authorization: Bearer <token>`.
- **`POST /api/login` response format changed**: Now returns
  `{ accessToken, expiresIn }` instead of setting a cookie. The refresh token
  is set as an HttpOnly cookie automatically.
- **`express-session` removed**: If any downstream code depends on `req.session`,
  it will break. Search for `req.session` usage before deploying.
