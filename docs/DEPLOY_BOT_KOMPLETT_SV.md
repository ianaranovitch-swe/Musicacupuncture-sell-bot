# Steg-för-steg: deploya botten (GitHub + GitHub Pages + Railway)

Den här guiden samlar **allt du behöver** om du kör **alternativ 2**: Mini App på **GitHub Pages**, boten på **Railway**, kod i **GitHub**.

---

## Del A — Kolla att filerna i repot är rätt

### A1. Obligatoriska filer för boten (Railway `worker`)

| Fil / mapp | Varför |
|------------|--------|
| `run_bot.py` | Startar Telegram-boten (`music_sales.bot_app`). |
| `requirements.txt` | Railway installerar beroenden härifrån. |
| `music_sales/` | Själva botlogiken. |
| `tracks.py` | Beskrivningar som matchar vetrinen (valfritt men bra). |
| `songs/` | **MP3-filer** som säljs — måste finnas på servern med samma namn som i katalogen (se `music_sales/catalog.py`). |
| `covers/` | **Omslagsbilder** för `/start` och Mini App — filnamn måste **exakt** matcha det som står i `tracks.py` / `miniapp.html` (se avsnitt A4). |

### A2. Filer för Mini App på GitHub Pages

| Fil | Varför |
|-----|--------|
| `miniapp.html` | Telegram Mini App (butik). |
| `covers/*.jpg` (eller png) | Bilder som `miniapp.html` länkar till — måste finnas i repot om du vill att omslag ska visas på Pages. |
| `.github/workflows/deploy-miniapp-pages.yml` | Automatisk publicering till Pages. |

### A3. Filer för Stripe `/buy` + webhook (valfritt, Railway `web`)

| Fil | Varför |
|-----|--------|
| `run_server.py` | Startar Flask + Stripe-rutter. |
| `music_sales/server.py` | `/create-checkout`, `/webhook`, m.m. |

### A4. Viktigt: omslagsfilnamn

Mini App och boten använder sökvägar som `covers/Divine sound Heart from God.jpg`.  
Om din fil heter t.ex. `1) Divine sound ...jpg` **matchar den inte** — då får du trasiga bilder. Byt namn så det blir **exakt** som i `tracks.py` (`cover`-fältet) och samma i `miniapp.html`.

### A5. GitHub Actions (CI)

| Fil | Varför |
|-----|--------|
| `.github/workflows/ci.yml` | Kör `pytest` vid push/PR — bra att den är grön innan du litar på en deploy. |

**OBS:** Lägg **aldrig** `BOT_TOKEN`, `STRIPE_SECRET_KEY` eller liknande i GitHub-filer som committas. Använd **Railway Variables** (eller GitHub **Secrets** endast om du bygger något som verkligen behöver dem — denna bot behöver det normalt **inte** i Actions).

---

## Del B — GitHub (kod + Mini App)

### B1. Skapa / använd repo

1. Skapa ett repo på GitHub (eller använd befintligt).
2. Lägg in hela projektet (inkl. `miniapp.html`, `covers/`, `songs/` om du vill att Railway ska få ljudfiler från git — **stora filer**: överväg Git LFS eller ladda upp `songs/` separat till Railway volume; annars funkar det om repot klarar storleken).

### B2. Aktivera GitHub Pages (för Mini App)

1. GitHub → ditt repo → **Settings** → **Pages**.
2. **Build and deployment** → **Source**: välj **GitHub Actions**.

### B3. Publicera Mini App

1. **Actions** → **Deploy Mini App (GitHub Pages)** → **Run workflow** (första gången), eller pusha ändringar i `miniapp.html` / `covers/`.
2. Vänta tills jobbet är **grönt**.
3. Under samma körning (eller i **Settings → Pages**) ser du ungefär:  
   `https://<användare>.github.io/<repo>/`  
4. Din Mini App-URL blir t.ex.:  
   **`https://<användare>.github.io/<repo>/miniapp.html`**

### B4. Första gången: miljön `github-pages`

Om GitHub frågar om godkännande för miljön **github-pages**: godkänn, eller gå till **Settings → Environments → github-pages** och ställ in regler.

---

## Del C — Railway (boten = `worker`)

### C1. Ny tjänst från GitHub

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Välj repot och grenen (t.ex. `main`).

### C2. Startkommando

1. Öppna tjänsten → **Settings** (kugghjul) → **Deploy** (eller **Start Command** beroende på UI).
2. Sätt: **`python run_bot.py`**  
   (Inte `bot.py` om du vill ha samma bot som i projektet med Stripe-köp via `/buy` — `run_bot.py` är den som används i `Procfile` som `worker`.)

### C3. Miljövariabler (minimikrav)

Lägg under **Variables**:

| Variabel | Exempel / förklaring |
|----------|----------------------|
| `BOT_TOKEN` | Från @BotFather (hemlig). |
| `OWNER_TELEGRAM_ID` | Ditt numeriska Telegram-ID (aviseringar). |
| `AUDIO_SALES_DIR` | `songs` (standard). |
| `LOG_LEVEL` | `INFO` |
| `LOG_FILE` | `-` (loggar till Railway-konsolen; bra i produktion). |
| `MINIAPP_URL` | **`https://<användare>.github.io/<repo>/miniapp.html`** (HTTPS, exakt som Pages-URL). |

**Valfritt** (om du senare lägger till `web` för checkout + webhook):

| Variabel | När |
|----------|-----|
| `STRIPE_SECRET_KEY` | Checkout + webhook. |
| `STRIPE_WEBHOOK_SECRET` | Webhook-signatur i produktion. |
| `BACKEND_URL` | URL till din `web`-tjänst, t.ex. `https://xxx.up.railway.app`. |
| `DOMAIN` | Samma som `web`-publik URL (HTTPS). |
| `PAYMENTS_PROVIDER_TOKEN` | Endast om du använder Telegram Payments via BotFather. |

### C4. Deploy

1. Spara variabler — Railway bygger om och startar.
2. **Deployments** → öppna senaste deploy → **View logs**.
3. Leta efter att boten startar (polling) utan fel.

---

## Del D — (Valfritt) Railway `web` för Stripe checkout + webhook

Gör detta bara om du vill att `/buy` skapar sessions via din backend och att webhook skickar MP3 efter betalning.

1. **New service** i samma projekt → samma GitHub-repo.
2. Startkommando: **`python run_server.py`**
3. Variabler: `BOT_TOKEN`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `DOMAIN=https://<web-service>.up.railway.app`
4. I **worker**-tjänsten: sätt `BACKEND_URL` och `DOMAIN` till samma `https://...` som `web`.
5. I Stripe: webhook URL `https://<web-service>.up.railway.app/webhook`, event `checkout.session.completed`.

Mer detalj: se `DEPLOY_RAILWAY.md` i repots rot.

---

## Del E — Telegram (BotFather)

1. **@BotFather** → `/mybots` → välj bot.
2. **Bot Settings** → **Menu Button** / **Configure Mini App** (eller motsvarande meny) — ange URL:  
   `https://<användare>.github.io/<repo>/miniapp.html`
3. Lägg till **domänen** för Web Apps (t.ex. `dittnamn.github.io`) om BotFather frågar — ska matcha din Pages-URL.

---

## Del F — Snabbtest efter deploy

1. Telegram: skicka **`/start`** till boten.
2. Kontrollera att **Open Music Store** finns och öppnar Mini App.
3. Öppna ett spår — kontrollera att **omslag** laddas (om inte: filnamn i `covers/` + push + vänta på Pages-deploy).
4. **Buy Now** — ska öppna Stripe-länk i webbläsare.

---

## Del G — Felsökning (kort)

| Problem | Trolig orsak |
|---------|----------------|
| Mini App öppnas inte | `MINIAPP_URL` saknas, fel HTTP (måste HTTPS), eller domän inte godkänd i BotFather. |
| Grå bilder / 404 | Fel filnamn i `covers/` jämfört med `tracks.py` / `miniapp.html`; eller Pages-deploy inte klar. |
| Bot svarar inte | Fel `BOT_TOKEN`, fel startkommando, eller krasch — läs Railway-loggar. |
| `/buy` funkar inte | `BACKEND_URL` / `web` / Stripe inte konfigurerat. |

---

## Snabbreferens: vad körs var?

| Plats | Vad |
|-------|-----|
| **GitHub** | Kod + CI + (valfritt) Pages-workflow. |
| **GitHub Pages** | `miniapp.html` + `covers/` (statisk butik). |
| **Railway worker** | `python run_bot.py` — Telegram polling. |
| **Railway web** | `python run_server.py` — Stripe API + webhook (valfritt). |

Mer om endast Mini App på Pages: `docs/DEPLOY_MINIAPP_GITHUB_PAGES_SV.md`.
