# Test Credentials

## President / Admin (seeded on startup)
- Email: `president@aureus.ai`
- Password: `Aureus2020!`
- Role: `president`

## Auth endpoints
- POST /api/auth/register  (email, password, name) -> creates `trader` role
- POST /api/auth/login      (email, password)
- POST /api/auth/logout
- GET  /api/auth/me         (cookie or Bearer)

Auth uses httpOnly cookies (access + refresh) and also accepts `Authorization: Bearer <token>`.
