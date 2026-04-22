# =========================
# VERSION 2 – TELEGRAM MUSIC STORE (AUTO CATALOG + UI)
# =========================

# =========================
# FILE: bot.py
# =========================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
import requests

BOT_TOKEN = "YOUR_NEW_TELEGRAM_BOT_TOKEN"
BACKEND_URL = "http://localhost:5000"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = requests.get(f"{BACKEND_URL}/songs")
    songs = response.json()

    keyboard = []
    for s in songs:
        keyboard.append([
            InlineKeyboardButton(f"🎵 {s['name']} ({s['price']} SEK)", callback_data=f"buy_{s['id']}"),
            InlineKeyboardButton("▶ Preview", callback_data=f"preview_{s['id']}")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎧 *Välkommen till min musikbutik*\n\nVälj en låt:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data.startswith("buy_"):
        song_id = data.split("_")[1]

        response = requests.post(f"{BACKEND_URL}/create-checkout", json={
            "song_id": song_id,
            "telegram_id": user_id
        })

        payment_url = response.json().get("url")

        await query.message.reply_text(f"💳 Betala här:\n{payment_url}")

    elif data.startswith("preview_"):
        song_id = data.split("_")[1]

        response = requests.get(f"{BACKEND_URL}/preview/{song_id}")
        preview_url = response.json().get("preview")

        await query.message.reply_audio(audio=preview_url, title="Preview")


app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_buttons))

app.run_polling()


# =========================
# FILE: server.py
# =========================

from flask import Flask, request, jsonify, send_file
import stripe
from telegram import Bot
import os

app = Flask(__name__)

stripe.api_key = "sk_test_REPLACE_WITH_SECRET"
BOT_TOKEN = "YOUR_NEW_TELEGRAM_BOT_TOKEN"
bot = Bot(token=BOT_TOKEN)

DOMAIN = "http://localhost:5000"
SONG_FOLDER = "songs"

# AUTO LOAD SONGS
songs = {}

for file in os.listdir(SONG_FOLDER):
    if file.endswith(".mp3"):
        song_id = file.replace(".mp3", "")
        songs[song_id] = {
            "id": song_id,
            "name": song_id,
            "price": 5000,
            "file": f"{SONG_FOLDER}/{file}",
            "preview": f"{DOMAIN}/preview-file/{song_id}"
        }

@app.route("/songs")
def get_songs():
    return jsonify(list(songs.values()))


@app.route("/preview/<song_id>")
def preview(song_id):
    return jsonify({"preview": songs[song_id]["preview"]})


@app.route("/preview-file/<song_id>")
def preview_file(song_id):
    return send_file(songs[song_id]["file"])


@app.route("/create-checkout", methods=["POST"])
def create_checkout():
    data = request.json
    song_id = data["song_id"]
    telegram_id = data["telegram_id"]

    song = songs[song_id]

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'sek',
                'product_data': {'name': song['name']},
                'unit_amount': song['price'],
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=DOMAIN + '/success',
        cancel_url=DOMAIN + '/cancel',
        metadata={
            "telegram_id": telegram_id,
            "song_id": song_id
        }
    )

    return jsonify({"url": session.url})


@app.route('/webhook', methods=['POST'])
def webhook():
    event = stripe.Event.construct_from(request.json, stripe.api_key)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        telegram_id = session['metadata']['telegram_id']
        song_id = session['metadata']['song_id']

        song = songs[song_id]

        with open(song['file'], 'rb') as audio:
            bot.send_audio(
                chat_id=telegram_id,
                audio=audio,
                title=song['name']
            )

    return '', 200


@app.route('/success')
def success():
    return "Payment successful"


@app.route('/cancel')
def cancel():
    return "Payment cancelled"


if __name__ == '__main__':
    app.run(port=5000)


# =========================
# REQUIREMENTS
# =========================

# pip install python-telegram-bot flask stripe requests


# =========================
# IMPROVEMENTS IN VERSION 2
# =========================

# ✅ Automatisk katalog (lägger du in MP3 → syns direkt i bot)
# ✅ Preview-knapp
# ✅ Snygg UI med emojis
# ✅ Mindre manuell kod
# ✅ Skalbar struktur


# =========================
# NEXT IDEAS (VERSION 3)
# =========================

# - Unika nedladdningslänkar
# - Databas (SQLite)
# - Adminpanel
# - Rabattkoder
# - Prenumeration
