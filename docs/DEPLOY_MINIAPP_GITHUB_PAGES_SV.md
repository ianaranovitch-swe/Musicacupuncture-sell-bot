# Mini App på GitHub Pages (alternativ 2)

Den här guiden visar hur du hostar **bara** vetrinen (`miniapp.html` + mappen `covers/`) på GitHub Pages. **Railway `web` behövs inte** för att öppna butiken i Telegram — men du behöver fortfarande `web` om du vill köra Stripe `/create-checkout` och webhook på Railway.

## 1. Förbered repo

1. Lägg alla omslagsbilder i **`covers/`** i repot (samma filnamn som i `tracks.py` / `miniapp.html`).
2. Pusha till GitHub (gren `main` eller `experiment` — samma som i workflow).

## 2. Slå på GitHub Pages

1. På GitHub: **Settings** → **Pages** (under *Code and automation*).
2. Under **Build and deployment**:
   - **Source**: välj **GitHub Actions** (inte “Deploy from a branch”).
3. Första gången kan du behöva godkänna miljön **github-pages** när workflow körs (GitHub visar en prompt).

## 3. Kör deploy

- **Automatiskt**: varje push till `main` / `experiment` som ändrar `miniapp.html`, `covers/**` eller workflow-filen startar deploy.
- **Manuellt**: **Actions** → workflow **Deploy Mini App (GitHub Pages)** → **Run workflow**.

När jobbet är grönt finns sidan på din Pages-URL.

## 4. Din URL till Telegram

### Vanligt repo (t.ex. `github.com/dittnamn/music-bot`)

- Bas: `https://dittnamn.github.io/music-bot/`
- Mini App (använd denna i BotFather / `MINIAPP_URL`):
  - **`https://dittnamn.github.io/music-bot/miniapp.html`**
  - eller **`https://dittnamn.github.io/music-bot/`** (samma innehåll som `index.html` kopieras från `miniapp.html` i workflow).

### User site (`github.com/dittnamn/dittnamn.github.io`)

- Bas: `https://dittnamn.github.io/`
- Mini App: **`https://dittnamn.github.io/miniapp.html`**

## 5. BotFather

1. Öppna **@BotFather** → din bot → **Bot Settings** → **Configure Mini App** / domän för Web Apps (beroende på meny i BotFather).
2. Lägg till **samma domän** som i URL:en (t.ex. `dittnamn.github.io`).

## 6. Miljövariabler (Railway worker — boten)

Sätt **HTTPS**-URL (Telegram kräver det):

```env
MINIAPP_URL=https://dittnamn.github.io/music-bot/miniapp.html
```

Du kan lämna `DOMAIN` på Railway som din Stripe-webb om du fortfarande kör `web` där; Mini App påverkas av `MINIAPP_URL`.

## 7. Felsökning

| Problem | Åtgärd |
|--------|--------|
| 404 på bilder | Kontrollera att filerna finns i `covers/` i repot och att namnen matchar exakt (inkl. mellanslag). |
| Workflow kräver godkännande | **Settings** → **Environments** → **github-pages** → lägg till regler eller godkänn körning. |
| Gammal sida i Telegram | Hård uppdatering / vänta på CDN; ändra t.ex. en kommentar i `miniapp.html` och pusha om. |

## 8. Säkerhet

Checkout-länkar i Mini App är publika — det är normalt för Stripe Payment Links. Lägg **aldrig** hemliga nycklar (`sk_live_…`) i `miniapp.html`.
