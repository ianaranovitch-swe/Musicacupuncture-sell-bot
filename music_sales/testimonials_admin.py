"""
Админка отзывов: /admin → Manage Reviews.
Сохранение в testimonials.py в корне репозитория.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from music_sales.admin_log import append_admin_log
from music_sales.admin_panel import is_admin
from music_sales.testimonials_store import (
    find_testimonial_by_id,
    format_telegram_review,
    load_all_testimonials,
    next_testimonial_id,
    save_testimonials,
)

logger = logging.getLogger(__name__)

# То же состояние, что ST_MAIN в admin_panel (0).
_ST_MAIN = 0

RV_STEP = "rv_step"
RV_EDIT_ID = "rv_edit_id"
RV_DELETE_ID = "rv_delete_id"


def _is_admin(user_id: int | None) -> bool:
    return is_admin(user_id)


def _log(uid: int, action: str, detail: dict | None = None) -> None:
    try:
        append_admin_log(user_id=uid, action=action, detail=detail)
    except Exception:
        logger.exception("admin_log failed")


def _reviews_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 View all reviews", callback_data="adm:rv:list")],
            [InlineKeyboardButton("➕ Add new review", callback_data="adm:rv:add")],
            [InlineKeyboardButton("✏️ Edit review", callback_data="adm:rv:edit")],
            [InlineKeyboardButton("🗑️ Delete review", callback_data="adm:rv:del")],
            [InlineKeyboardButton("👁 Toggle visible/hidden", callback_data="adm:rv:toggle")],
            [InlineKeyboardButton("◀️ Back to admin menu", callback_data="adm:menu")],
        ]
    )


def _review_summary_line(item: dict[str, Any]) -> str:
    vis = "✅" if item.get("visible", True) is not False else "🚫"
    return f"{vis} #{item.get('id')} — {item.get('name')} ({item.get('city')}) — {item.get('track')}"


async def show_reviews_admin_menu(message, uid: int) -> None:
    _log(uid, "reviews_admin_open")
    await message.reply_text(
        "⭐ Manage Reviews\n\n"
        "Reviews sync to testimonials.json and TESTIMONIALS_JSON (set the same env on bot + web on Railway). "
        "Hidden reviews (🚫) are not shown on the website or in the bot.",
        reply_markup=_reviews_menu_kb(),
    )


async def testimonials_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка adm:rv:* внутри админ-диалога."""
    q = update.callback_query
    if q is None or q.data is None or q.message is None:
        return _ST_MAIN
    uid = q.from_user.id if q.from_user else None
    if not _is_admin(uid):
        await q.answer("Access denied", show_alert=True)
        return _ST_MAIN
    await q.answer()
    data = q.data
    context.user_data.pop(RV_DELETE_ID, None)

    if data == "adm:rv:list":
        items = load_all_testimonials()
        if not items:
            await q.message.reply_text("No reviews yet.", reply_markup=_reviews_menu_kb())
            return _ST_MAIN
        lines = ["📋 All reviews:\n"] + [_review_summary_line(t) for t in sorted(items, key=lambda x: int(x.get("id") or 0))]
        chunk = "\n".join(lines)
        if len(chunk) > 4000:
            chunk = chunk[:3990] + "…"
        await q.message.reply_text(chunk, reply_markup=_reviews_menu_kb())
        return _ST_MAIN

    if data == "adm:rv:add":
        context.user_data[RV_STEP] = "add_name"
        context.user_data.pop(RV_EDIT_ID, None)
        await q.message.reply_text("Add review — send customer name (e.g. Sarah M.):")
        return _ST_MAIN

    if data == "adm:rv:edit":
        context.user_data[RV_STEP] = "edit_pick"
        await q.message.reply_text("Edit review — send numeric review ID:")
        return _ST_MAIN

    if data == "adm:rv:del":
        context.user_data[RV_STEP] = "del_pick"
        await q.message.reply_text("Delete review — send numeric review ID:")
        return _ST_MAIN

    if data == "adm:rv:toggle":
        context.user_data[RV_STEP] = "toggle_pick"
        await q.message.reply_text("Toggle visibility — send numeric review ID:")
        return _ST_MAIN

    if data.startswith("adm:rv:toggle:"):
        try:
            tid = int(data.split(":")[-1])
        except ValueError:
            return _ST_MAIN
        items = load_all_testimonials()
        row = find_testimonial_by_id(items, tid)
        if not row:
            await q.message.reply_text("Review not found.", reply_markup=_reviews_menu_kb())
            return _ST_MAIN
        row["visible"] = not (row.get("visible", True) is not False)
        save_testimonials(items)
        _log(uid or 0, "review_toggle", {"id": tid, "visible": row["visible"]})
        await q.message.reply_text(
            f"Review #{tid} is now {'visible' if row['visible'] else 'hidden'}.",
            reply_markup=_reviews_menu_kb(),
        )
        return _ST_MAIN

    if data.startswith("adm:rv:delok:"):
        try:
            tid = int(data.split(":")[-1])
        except ValueError:
            return _ST_MAIN
        items = [t for t in load_all_testimonials() if int(t.get("id", -1)) != tid]
        save_testimonials(items)
        _log(uid or 0, "review_delete", {"id": tid})
        await q.message.reply_text(f"Deleted review #{tid}.", reply_markup=_reviews_menu_kb())
        return _ST_MAIN

    if data == "adm:rv:delcancel":
        await q.message.reply_text("Delete cancelled.", reply_markup=_reviews_menu_kb())
        return _ST_MAIN

    if data == "adm:rv:save_draft":
        draft = context.user_data.get("rv_draft") or {}
        text = str(draft.get("text") or "").strip()
        if not text or not draft.get("name"):
            await q.message.reply_text("Nothing to save. Start again with Add new review.", reply_markup=_reviews_menu_kb())
            context.user_data.pop(RV_STEP, None)
            context.user_data.pop("rv_draft", None)
            return _ST_MAIN
        items = load_all_testimonials()
        new_id = next_testimonial_id(items)
        items.append(
            {
                "id": new_id,
                "name": draft.get("name", ""),
                "city": draft.get("city", ""),
                "track": draft.get("track", ""),
                "rating": int(draft.get("rating") or 5),
                "visible": True,
                "text": text,
            }
        )
        save_testimonials(items)
        context.user_data.pop(RV_STEP, None)
        context.user_data.pop("rv_draft", None)
        _log(uid or 0, "review_add", {"id": new_id})
        await q.message.reply_text(
            f"✅ Saved review #{new_id}.\n"
            "Bot: updated immediately.\n"
            "Website: updates after Railway sync + web redeploy "
            "(ENABLE_TESTIMONIALS_RAILWAY_SYNC=1, shared or dual service ids).",
            reply_markup=_reviews_menu_kb(),
        )
        return _ST_MAIN

    if data == "adm:rv:cancel_draft":
        context.user_data.pop(RV_STEP, None)
        context.user_data.pop("rv_draft", None)
        await q.message.reply_text("Add review cancelled.", reply_markup=_reviews_menu_kb())
        return _ST_MAIN

    return _ST_MAIN


async def testimonials_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Текстовые шаги мастера добавления/редактирования отзыва."""
    if update.message is None or update.effective_user is None:
        return _ST_MAIN
    if not _is_admin(update.effective_user.id):
        return _ST_MAIN
    step = context.user_data.get(RV_STEP)
    if not step:
        return _ST_MAIN

    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    draft = context.user_data.setdefault("rv_draft", {})

    if step == "add_name":
        draft.clear()
        draft["name"] = text
        context.user_data[RV_STEP] = "add_city"
        await update.message.reply_text("City:")
        return _ST_MAIN

    if step == "add_city":
        draft["city"] = text
        context.user_data[RV_STEP] = "add_track"
        await update.message.reply_text("Track title (exact name, e.g. Divine sound Heart from God):")
        return _ST_MAIN

    if step == "add_track":
        draft["track"] = text
        context.user_data[RV_STEP] = "add_text"
        await update.message.reply_text("Review text (full quote):")
        return _ST_MAIN

    if step == "add_text":
        draft["text"] = text
        draft["rating"] = 5
        context.user_data[RV_STEP] = "add_confirm"
        preview_item = {
            "id": 0,
            "name": draft.get("name", ""),
            "city": draft.get("city", ""),
            "track": draft.get("track", ""),
            "rating": draft.get("rating", 5),
            "text": text,
        }
        preview = format_telegram_review(preview_item, index=1, total=1)
        kb = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("💾 Save new review", callback_data="adm:rv:save_draft")],
                [InlineKeyboardButton("Cancel", callback_data="adm:rv:cancel_draft")],
            ]
        )
        await update.message.reply_text(
            "Preview — tap Save to store this review in the bot and website:\n\n" + preview,
            reply_markup=kb,
        )
        return _ST_MAIN

    if step == "edit_pick":
        try:
            tid = int(text)
        except ValueError:
            await update.message.reply_text("Send a numeric ID.")
            return _ST_MAIN
        if not find_testimonial_by_id(load_all_testimonials(), tid):
            await update.message.reply_text("Review not found.")
            return _ST_MAIN
        context.user_data[RV_EDIT_ID] = tid
        context.user_data[RV_STEP] = "edit_field"
        await update.message.reply_text("Field to edit: name | city | track | text | rating")
        return _ST_MAIN

    if step == "edit_field":
        draft["field"] = text.lower()
        context.user_data[RV_STEP] = "edit_value"
        await update.message.reply_text(f"New value for {draft.get('field')}:")
        return _ST_MAIN

    if step == "edit_value":
        tid = int(context.user_data.get(RV_EDIT_ID) or 0)
        field = str(draft.get("field") or "")
        items = load_all_testimonials()
        row = find_testimonial_by_id(items, tid)
        if not row or field not in ("name", "city", "track", "text", "rating"):
            await update.message.reply_text("Invalid field or review.", reply_markup=_reviews_menu_kb())
            context.user_data.pop(RV_STEP, None)
            return _ST_MAIN
        if field == "rating":
            try:
                row["rating"] = max(1, min(5, int(text)))
            except ValueError:
                await update.message.reply_text("Rating must be 1–5.")
                return _ST_MAIN
        else:
            row[field] = text
        save_testimonials(items)
        context.user_data.pop(RV_STEP, None)
        _log(uid, "review_edit", {"id": tid, "field": field})
        await update.message.reply_text(f"✅ Updated review #{tid}.", reply_markup=_reviews_menu_kb())
        return _ST_MAIN

    if step == "del_pick":
        try:
            tid = int(text)
        except ValueError:
            await update.message.reply_text("Send a numeric ID.")
            return _ST_MAIN
        if not find_testimonial_by_id(load_all_testimonials(), tid):
            await update.message.reply_text("Review not found.")
            return _ST_MAIN
        context.user_data[RV_DELETE_ID] = tid
        context.user_data.pop(RV_STEP, None)
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Delete", callback_data=f"adm:rv:delok:{tid}"),
                    InlineKeyboardButton("Cancel", callback_data="adm:rv:delcancel"),
                ]
            ]
        )
        await update.message.reply_text(f"Delete review #{tid}?", reply_markup=kb)
        return _ST_MAIN

    if step == "toggle_pick":
        try:
            tid = int(text)
        except ValueError:
            await update.message.reply_text("Send a numeric ID.")
            return _ST_MAIN
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Toggle now", callback_data=f"adm:rv:toggle:{tid}")]]
        )
        context.user_data.pop(RV_STEP, None)
        await update.message.reply_text(f"Toggle visibility for review #{tid}?", reply_markup=kb)
        return _ST_MAIN

    return _ST_MAIN
