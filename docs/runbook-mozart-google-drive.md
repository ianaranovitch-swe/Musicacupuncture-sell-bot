# Runbook: Mozart MP3 on Google Drive (website download)

## Why this is needed

All shop MP3s are **26–50 MB**. Telegram Bot API `getFile` (used by the website after Stripe) only allows about **20 MB**. Website download uses Google Drive via the service account.

## Current mapping

Drive file IDs for **all 32 tracks** (classic 1–18 + Mozart 19–32) live in `tracks.py` → `_BUILTIN_GOOGLE_DRIVE_IDS`.

Note: there are two Drive folders named `musicacupuncture-mp3`:

- `jan@kvantmr.online` — classic Divine sound (ids 1–18)
- `ianarastockholm@gmail.com` — Mozart / Super Mozart (ids 19–32)

Both must stay shared with the shop service account (Viewer):

`mp3-downloader-latest@mp3-shop.iam.gserviceaccount.com`

After changing IDs, redeploy the **Web** service on Railway so `tracks.py` is live.

## If a new MP3 is added later

1. Upload it to the shared folder.
2. Share the folder with the service account (Viewer) if it is a new folder.
3. Copy the file ID from `https://drive.google.com/file/d/FILE_ID/view`
4. Add it to `_BUILTIN_GOOGLE_DRIVE_IDS` in `tracks.py`.
