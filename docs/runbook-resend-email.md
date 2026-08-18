# Runbook: Resend purchase emails

## What it does

After a successful Stripe Checkout payment the bot/web service sends branded HTML emails
(plus plain-text fallback) from `music_sales/email_templates.py`:

1. **Buyer** — personalized greeting (from Telegram `@name` or email local-part), track, amount, Drive download button
2. **Shop owner** — `SHOP_OWNER_EMAIL` (eyebrow: “shop owner”)
3. **Developer** — `DEVELOPER_EMAIL` (eyebrow: “developer notify”; skipped if address already in owner list)

Transport: **Resend HTTP API** (`POST https://api.resend.com/emails`) with both `html` and `text`.

## Railway / .env variables

| Variable | Required | Example |
|----------|----------|---------|
| `ENABLE_PURCHASE_EMAIL` | yes | `1` |
| `RESEND_API_KEY` | yes | `re_...` |
| `RESEND_FROM` | yes | `Music Acupuncture <orders@yourdomain.com>` |
| `SHOP_OWNER_EMAIL` | recommended | `owner@gmail.com` |
| `DEVELOPER_EMAIL` | recommended | `you@gmail.com` |
| `SUPPORT_CONTACT` | optional | shown in buyer email |
| `EMAIL_STARTUP_TEST` | optional | `1` (default when emails on) / `0` to skip |

Set these on **both** Railway services that handle payments (typically **Web** that receives Stripe webhooks). Redeploy after saving.

## Setup checklist

1. Create account at https://resend.com
2. Add and verify your sending domain (DNS records from Resend)
3. Create an API key → copy to `RESEND_API_KEY`
4. Set `RESEND_FROM` to an address on that verified domain
5. Set owner + developer emails
6. Set `ENABLE_PURCHASE_EMAIL=1`
7. Redeploy; check logs for `Email startup test: SUCCESS`
8. Do a small Stripe test purchase; confirm three mailboxes (or two if owner=dev)

## Logs to look for

- `purchase email: start …`
- `Resend: message accepted for delivery …`
- `purchase email: staff notified …` / `buyer notified …`

## Notes

- Telegram in-app payments often have **no** buyer email → only staff emails are sent.
- Website Stripe Checkout collects email → buyer receipt is sent.
- Old `GMAIL_USER` / `GMAIL_PASSWORD` are no longer used.
