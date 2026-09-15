import os
import json
import html
import base64
from datetime import datetime

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DEVELOPER = os.environ.get("DEVELOPER", "@GpsirEra")
BOT_TITLE = "GpSirEra Referral Joining Giveaway"

WELCOME_BANNER_URL = "https://i.ibb.co/k2GWFvBp/file-00000000256481fabb87306e88d17cf8.png"

ADMIN_USERS = [8932695749] + [
    int(x) for x in os.environ.get("ADMIN_USERS", "").split(",") if x.strip().isdigit()
]

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Bot-wide required channel/chat before ANY use of the bot.
REQUIRED_CHATS = [
    {
        "chat_id": -1004485651677,
        "title": "GpsirEra Community",
        "url": "https://t.me/Black_hats_ops",
        "request_based": False,
    },
    {
        "chat_id": -1003927824087,
        "title": "GpsirEra Community | Chat",
        "url": "https://t.me/+VXs73pFfyEphMzJl",
        "request_based": True,
    },
    {
        "chat_id": -1004297567227,
        "title": "GpsirEra Community | Channel",
        "url": "https://t.me/+0w8ATlAukVA1MWU1",
        "request_based": True,
    },
]

DIVIDER = "─" * 22

# ==================== COOL UNICODE FONT (no parse_mode needed, always safe) ====================
_BOLD_UPPER_START = 0x1D5D4
_BOLD_LOWER_START = 0x1D5EE
_BOLD_DIGIT_START = 0x1D7EC


def cool_bold(text):
    """Converts plain ASCII to Mathematical Sans-Serif Bold unicode chars.
    Pure unicode, not a markup entity - renders correctly regardless of
    parse_mode, so it can never trigger the offset/parsing bugs that HTML
    or Markdown formatting can."""
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr(_BOLD_UPPER_START + (ord(ch) - ord("A"))))
        elif "a" <= ch <= "z":
            out.append(chr(_BOLD_LOWER_START + (ord(ch) - ord("a"))))
        elif "0" <= ch <= "9":
            out.append(chr(_BOLD_DIGIT_START + (ord(ch) - ord("0"))))
        else:
            out.append(ch)
    return "".join(out)


# ==================== REDIS (Upstash REST) ====================
def _redis_headers():
    return {"Authorization": f"Bearer {UPSTASH_TOKEN}"}


def redis_get(key):
    if not UPSTASH_URL:
        return None
    r = requests.get(f"{UPSTASH_URL}/get/{key}", headers=_redis_headers(), timeout=10)
    return r.json().get("result")


def redis_set(key, value):
    if not UPSTASH_URL:
        return
    requests.post(f"{UPSTASH_URL}/set/{key}", headers=_redis_headers(), data=value, timeout=10)


def redis_del(key):
    if not UPSTASH_URL:
        return
    requests.get(f"{UPSTASH_URL}/del/{key}", headers=_redis_headers(), timeout=10)


def get_json(key, default):
    raw = redis_get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def set_json(key, value):
    redis_set(key, json.dumps(value))


# ==================== HELPERS ====================
def esc(s):
    return html.escape(str(s), quote=False)


def generate_id():
    return base64.urlsafe_b64encode(os.urandom(5)).decode("utf-8").rstrip("=")


def is_admin(user_id):
    return int(user_id) in ADMIN_USERS


def tg(method, payload):
    r = requests.post(f"{TELEGRAM_API}/{method}", json=payload, timeout=15)
    return r.json()


def send_message(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)


def send_photo(chat_id, photo_url, caption, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendPhoto", payload)


def edit_message(chat_id, message_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("editMessageText", payload)


def answer_callback(callback_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    return tg("answerCallbackQuery", payload)


def get_me_username():
    cached = redis_get("bot_username")
    if cached:
        return cached
    data = tg("getMe", {})
    username = data.get("result", {}).get("username", "")
    if username:
        redis_set("bot_username", username)
    return username


def kb(rows):
    return {"inline_keyboard": rows}


def btn(text, callback_data):
    return {"text": text, "callback_data": callback_data}


# ==================== FORCE-JOIN GATE (shared logic) ====================
def is_actual_member(chat_id, user_id):
    try:
        r = tg("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        status = r.get("result", {}).get("status")
        return status in ("member", "administrator", "creator")
    except Exception:
        return False


def has_pending_request(chat_id, user_id):
    requested = get_json(f"join_requests:{chat_id}", [])
    return user_id in requested


def missing_joins(user_id, extra_chats=None):
    """Checks REQUIRED_CHATS plus any giveaway-specific extra_chats."""
    chats = REQUIRED_CHATS + (extra_chats or [])
    missing = []
    for ch in chats:
        if ch.get("request_based"):
            if has_pending_request(ch["chat_id"], user_id) or is_actual_member(ch["chat_id"], user_id):
                continue
        else:
            if is_actual_member(ch["chat_id"], user_id):
                continue
        missing.append(ch)
    return missing


def send_join_prompt(chat_id, missing):
    rows = [[{"text": f"➕ Join {esc(ch['title'])}", "url": ch["url"]}] for ch in missing]
    rows.append([btn("✅ I've Joined", "checkjoin")])
    lines = "\n".join(f"• {esc(c['title'])}" for c in missing)
    text = (
        "🔒 <b>Access Locked</b>\n\n"
        "Please join the following before continuing:\n\n"
        f"{lines}\n\n"
        "After joining, tap the button below."
    )
    send_message(chat_id, text, reply_markup=kb(rows))


def handle_join_request(jr):
    chat_id = jr["chat"]["id"]
    user_id = jr["from"]["id"]
    key = f"join_requests:{chat_id}"
    requested = get_json(key, [])
    if user_id not in requested:
        requested.append(user_id)
        set_json(key, requested)


# ==================== USER TRACKING ====================
def is_known_user(user_id):
    all_users = get_json("all_users", {})
    return str(user_id) in all_users


def record_user_activity(user):
    uid = str(user.get("id"))
    all_users = get_json("all_users", {})
    now = datetime.now().isoformat()
    entry = all_users.get(uid, {
        "id": uid,
        "username": None,
        "first_name": None,
        "first_seen": now,
        "message_count": 0,
    })
    entry["username"] = user.get("username")
    entry["first_name"] = user.get("first_name")
    entry["last_seen"] = now
    entry["message_count"] = entry.get("message_count", 0) + 1
    all_users[uid] = entry
    set_json("all_users", all_users)


# ==================== GIVEAWAY DATA ====================
def get_giveaways():
    return get_json("giveaways", {})


def save_giveaways(data):
    set_json("giveaways", data)


def get_giveaway(gid):
    return get_giveaways().get(gid)


def get_participants(gid):
    return get_json(f"participants:{gid}", {})


def save_participants(gid, data):
    set_json(f"participants:{gid}", data)


def get_admin_wizard(admin_id):
    return get_json(f"wizard:{admin_id}", None)


def set_admin_wizard(admin_id, state):
    set_json(f"wizard:{admin_id}", state)


def clear_admin_wizard(admin_id):
    redis_del(f"wizard:{admin_id}")


# ==================== BAN SYSTEM ====================
def get_banned():
    return get_json("banned_users", {})


def save_banned(data):
    set_json("banned_users", data)


def is_banned(user_id):
    return str(user_id) in get_banned()


def ban_user(user_id, reason, admin_id):
    banned = get_banned()
    banned[str(user_id)] = {
        "reason": reason,
        "banned_at": datetime.now().isoformat(),
        "banned_by": admin_id,
    }
    save_banned(banned)


def unban_user(user_id):
    banned = get_banned()
    banned.pop(str(user_id), None)
    save_banned(banned)


# ==================== WELCOME ====================
def send_welcome(chat_id, user_id):
    title = cool_bold(BOT_TITLE)
    caption = (
        f"🎉 <b>{esc(title)}</b>\n"
        f"{DIVIDER}\n\n"
        "Join referral giveaways, share your personal link, and climb the "
        "leaderboard. First to reach the required referrals wins!\n\n"
        "<blockquote>📌 Every referral only counts once your friend joins "
        "our required channels first. Bringing in people who already use "
        "this bot doesn't count - only brand-new joins do.</blockquote>\n\n"
        f"Developer: {esc(DEVELOPER)}"
    )
    rows = [[btn("🎁 View Giveaways", "giveaways_list")], [btn("📊 My Stats", "mystats")]]
    if is_admin(user_id):
        rows.append([btn("🛠 Admin Panel", "admin_panel")])
    send_photo(chat_id, WELCOME_BANNER_URL, caption, reply_markup=kb(rows))


# ==================== GIVEAWAY LIST / JOIN ====================
def render_giveaways_list(chat_id, user_id, edit=None):
    giveaways = get_giveaways()
    active = {gid: g for gid, g in giveaways.items() if g["status"] == "active"}

    if not active and not is_admin(user_id):
        msg = "📭 No active giveaways right now. Check back soon!"
        if edit:
            edit_message(chat_id, edit, msg)
        else:
            send_message(chat_id, msg)
        return

    rows = []
    text = f"🎁 <b>{esc(cool_bold('Active Giveaways'))}</b>\n{DIVIDER}\n\n"
    if not active:
        text += "No active giveaways right now.\n\n"
    for gid, g in active.items():
        participants = get_participants(gid)
        text += (
            f"🏆 <b>{esc(g['title'])}</b>\n"
            f"{esc(g['description'])}\n"
            f"🎯 Required referrals to win: {g['required_points']}\n"
            f"👥 Participants: {len(participants)}\n\n"
        )
        rows.append([btn(f"➕ Join: {g['title'][:25]}", f"join_{gid}")])

    if is_admin(user_id):
        ended = {gid: g for gid, g in giveaways.items() if g["status"] == "ended"}
        rows.append([btn("🆕 Create New Giveaway", "newgiveaway")])
        for gid, g in giveaways.items():
            rows.append([btn(f"⚙️ Manage: {g['title'][:20]}", f"manage_{gid}")])
        rows.append([btn("🚫 Ban User", "banwizard"), btn("📋 Banned List", "bannedlist")])

    markup = kb(rows) if rows else None
    if edit:
        edit_message(chat_id, edit, text, reply_markup=markup)
    else:
        send_message(chat_id, text, reply_markup=markup)


def build_referral_block(gid, g, user_id):
    bot_username = get_me_username()
    link = f"https://t.me/{bot_username}?start=g{gid}_{user_id}"
    participants = get_participants(gid)
    my_points = participants.get(str(user_id), {}).get("points", 0)

    share_message = (
        f"🎁 {g['title']}\n"
        f"{g['description']}\n\n"
        f"👉 Join here: {link}\n"
        f"First to {g['required_points']} referrals wins! 🏆"
    )

    text = (
        f"✅ <b>You're in: {esc(g['title'])}</b>\n"
        f"{DIVIDER}\n\n"
        f"<blockquote>📌 <b>How to earn points</b>\n"
        "Share your referral link below. When someone joins using it AND "
        "completes the required channel joins, you get <b>+1 point</b> "
        "automatically. People who already use this bot don't count as new "
        "referrals.</blockquote>\n\n"
        f"📊 Your progress: <b>{my_points}/{g['required_points']}</b>\n\n"
        f"🔗 <b>Your referral link</b>\n<code>{esc(link)}</code>\n\n"
        f"📤 <b>Ready-to-share message</b> (tap to copy)\n<code>{esc(share_message)}</code>"
    )
    markup = kb([[btn("📊 My Stats", "mystats"), btn("🏆 Leaderboard", f"lb_{gid}")]])
    return text, markup


def process_join_giveaway(chat_id, user_id, gid, referrer_id=None, edit=None):
    g = get_giveaway(gid)
    if not g:
        msg = "❌ This giveaway doesn't exist or was removed."
        (edit_message(chat_id, edit, msg) if edit else send_message(chat_id, msg))
        return
    if g["status"] != "active":
        msg = "⌛ This giveaway has ended."
        (edit_message(chat_id, edit, msg) if edit else send_message(chat_id, msg))
        return

    extra_chats = g.get("required_channels", [])
    missing = missing_joins(user_id, extra_chats=extra_chats)
    if missing:
        if referrer_id:
            set_json(f"pending_join:{user_id}", {"gid": gid, "ref": referrer_id})
        else:
            set_json(f"pending_join:{user_id}", {"gid": gid, "ref": None})
        send_join_prompt(chat_id, missing)
        return

    participants = get_participants(gid)
    uid_str = str(user_id)
    is_new_participant = uid_str not in participants

    if is_new_participant:
        participants[uid_str] = {
            "points": 0,
            "referred_by": None,
            "joined_at": datetime.now().isoformat(),
        }

        # Award the referrer a point ONLY if:
        # - a referrer was actually supplied
        # - it isn't a self-referral
        # - the referrer is themselves a real participant of this giveaway
        # - this user was brand-new to the ENTIRE bot before this click
        #   (existing users clicking a friend's link don't count)
        was_brand_new_to_bot = not is_known_user(user_id)
        if (
            referrer_id
            and str(referrer_id) != uid_str
            and str(referrer_id) in participants
            and was_brand_new_to_bot
        ):
            participants[uid_str]["referred_by"] = str(referrer_id)
            ref_entry = participants[str(referrer_id)]
            ref_entry["points"] = ref_entry.get("points", 0) + 1
            save_participants(gid, participants)

            new_points = ref_entry["points"]
            try:
                send_message(
                    int(referrer_id),
                    f"🎉 Someone joined <b>{esc(g['title'])}</b> using your link!\n"
                    f"📊 Your progress: <b>{new_points}/{g['required_points']}</b>",
                )
            except Exception:
                pass

            if new_points >= g["required_points"]:
                notify_admins_of_winner_candidate(g, gid, referrer_id, new_points)

        save_participants(gid, participants)

    text, markup = build_referral_block(gid, g, user_id)
    if edit:
        edit_message(chat_id, edit, text, reply_markup=markup)
    else:
        send_message(chat_id, text, reply_markup=markup)


def notify_admins_of_winner_candidate(g, gid, user_id, points):
    for admin_id in ADMIN_USERS:
        try:
            send_message(
                admin_id,
                f"🏆 <b>Winner Candidate!</b>\n\n"
                f"User <code>{esc(user_id)}</code> just reached "
                f"<b>{points}/{g['required_points']}</b> referrals in "
                f"<b>{esc(g['title'])}</b>.\n\n"
                f"Use /giveaways → Manage → Pick Winner to confirm.",
            )
        except Exception:
            pass


def handle_mystats(chat_id, user_id):
    giveaways = get_giveaways()
    uid_str = str(user_id)
    lines = []
    for gid, g in giveaways.items():
        participants = get_participants(gid)
        if uid_str in participants:
            pts = participants[uid_str].get("points", 0)
            status = "🟢 Active" if g["status"] == "active" else "🔴 Ended"
            lines.append(f"🏆 <b>{esc(g['title'])}</b> ({status})\n📊 {pts}/{g['required_points']}\n")
    if not lines:
        send_message(chat_id, "📭 You haven't joined any giveaways yet. Use /giveaways to join one!")
        return
    text = f"📊 <b>{esc(cool_bold('My Stats'))}</b>\n{DIVIDER}\n\n" + "\n".join(lines)
    send_message(chat_id, text)


def handle_leaderboard(chat_id, gid, edit=None):
    g = get_giveaway(gid)
    if not g:
        msg = "❌ Giveaway not found."
        (edit_message(chat_id, edit, msg) if edit else send_message(chat_id, msg))
        return
    participants = get_participants(gid)
    ranked = sorted(participants.items(), key=lambda kv: kv[1].get("points", 0), reverse=True)[:15]

    text = f"🏆 <b>{esc(g['title'])} Leaderboard</b>\n{DIVIDER}\n\n"
    if not ranked:
        text += "No participants yet."
    for i, (uid, p) in enumerate(ranked, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        text += f"{medal} <code>{esc(uid)}</code> — {p.get('points', 0)} pts\n"

    if edit:
        edit_message(chat_id, edit, text)
    else:
        send_message(chat_id, text)


# ==================== ADMIN: GIVEAWAY CREATION WIZARD ====================
def start_new_giveaway_wizard(chat_id, admin_id):
    set_admin_wizard(admin_id, {"type": "newgiveaway", "step": "title"})
    send_message(chat_id, "🆕 <b>New Giveaway</b>\n\nSend the giveaway <b>title</b> (e.g. Telegram USA Account Giveaway).\nSend /cancel to stop.")


def start_ban_wizard(chat_id, admin_id):
    set_admin_wizard(admin_id, {"type": "ban", "step": "user_id"})
    send_message(chat_id, "🚫 <b>Ban a User</b>\n\nSend the numeric Telegram user ID to ban.\nSend /cancel to stop.")


def handle_wizard_text(message):
    chat_id = message["chat"]["id"]
    admin_id = message["from"]["id"]
    text = message.get("text", "").strip()

    state = get_admin_wizard(admin_id)
    if not state:
        return False  # not in a wizard, let normal routing handle it

    wtype = state.get("type", "newgiveaway")

    if text == "/cancel":
        clear_admin_wizard(admin_id)
        send_message(chat_id, "❌ Cancelled.")
        return True

    if wtype == "ban":
        return handle_ban_wizard_step(chat_id, admin_id, state, text)

    step = state["step"]

    if step == "title":
        state["title"] = text
        state["step"] = "description"
        set_admin_wizard(admin_id, state)
        send_message(chat_id, "📝 Now send the <b>description</b> for this giveaway.")
        return True

    if step == "description":
        state["description"] = text
        state["step"] = "points"
        set_admin_wizard(admin_id, state)
        send_message(chat_id, "🎯 How many referrals are required to win? Send a number (e.g. 10).")
        return True

    if step == "points":
        if not text.isdigit() or int(text) <= 0:
            send_message(chat_id, "❌ Please send a positive whole number.")
            return True
        state["required_points"] = int(text)
        state["step"] = "channels"
        set_admin_wizard(admin_id, state)
        send_message(
            chat_id,
            "📢 Any EXTRA required channel just for this giveaway?\n\n"
            "Send as: <code>chat_id|title|url</code>\n"
            "Or send <code>skip</code> if none.",
        )
        return True

    if step == "channels":
        if text.lower() == "skip":
            finalize_giveaway(chat_id, admin_id, state)
            return True
        parts = text.split("|")
        if len(parts) != 3 or not parts[0].strip().lstrip("-").isdigit():
            send_message(chat_id, "❌ Format must be: chat_id|title|url  (or send 'skip')")
            return True
        state.setdefault("required_channels", []).append(
            {"chat_id": int(parts[0].strip()), "title": parts[1].strip(), "url": parts[2].strip(), "request_based": False}
        )
        set_admin_wizard(admin_id, state)
        send_message(chat_id, "✅ Added. Send another as chat_id|title|url, or 'skip' to finish.")
        return True

    return True


def finalize_giveaway(chat_id, admin_id, state):
    gid = generate_id()
    giveaways = get_giveaways()
    giveaways[gid] = {
        "id": gid,
        "title": state["title"],
        "description": state["description"],
        "required_points": state["required_points"],
        "required_channels": state.get("required_channels", []),
        "status": "active",
        "winners": [],
        "created_at": datetime.now().isoformat(),
    }
    save_giveaways(giveaways)
    clear_admin_wizard(admin_id)

    bot_username = get_me_username()
    text = (
        f"✅ <b>Giveaway Created!</b>\n{DIVIDER}\n\n"
        f"🏆 {esc(state['title'])}\n"
        f"📝 {esc(state['description'])}\n"
        f"🎯 Required: {state['required_points']} referrals\n"
        f"🆔 <code>{gid}</code>\n\n"
        f"It's now live. Use /giveaways to manage it."
    )
    send_message(chat_id, text)


def handle_ban_wizard_step(chat_id, admin_id, state, text):
    step = state["step"]

    if step == "user_id":
        if not text.isdigit():
            send_message(chat_id, "❌ Send a numeric user ID only.")
            return True
        state["target_id"] = text
        state["step"] = "reason"
        set_admin_wizard(admin_id, state)
        send_message(chat_id, f"📝 Send the ban reason for user <code>{esc(text)}</code>.")
        return True

    if step == "reason":
        target_id = state["target_id"]
        reason = text
        ban_user(target_id, reason, admin_id)
        clear_admin_wizard(admin_id)
        send_message(
            chat_id,
            f"🚫 <b>User Banned</b>\n\n"
            f"🆔 <code>{esc(target_id)}</code>\n"
            f"📝 Reason: {esc(reason)}",
        )
        try:
            send_message(
                int(target_id),
                f"🚫 <b>You have been banned from using this bot.</b>\n\n"
                f"📝 Reason: {esc(reason)}\n\n"
                f"Contact {esc(DEVELOPER)} if you believe this is a mistake.",
            )
        except Exception:
            pass
        return True

    return True


# ==================== ADMIN: MANAGE ====================
def render_manage_giveaway(chat_id, gid, edit=None):
    g = get_giveaway(gid)
    if not g:
        msg = "❌ Giveaway not found."
        (edit_message(chat_id, edit, msg) if edit else send_message(chat_id, msg))
        return
    participants = get_participants(gid)
    status_label = "🟢 Active" if g["status"] == "active" else "🔴 Ended"

    text = (
        f"⚙️ <b>Manage: {esc(g['title'])}</b>\n{DIVIDER}\n\n"
        f"Status: {status_label}\n"
        f"🎯 Required: {g['required_points']} referrals\n"
        f"👥 Participants: {len(participants)}\n"
        f"🏆 Winners so far: {len(g.get('winners', []))}\n"
    )
    rows = [
        [btn("🏆 Leaderboard", f"lb_{gid}"), btn("🎖 Pick Winner", f"winner_{gid}")],
    ]
    if g["status"] == "active":
        rows.append([btn("🔴 End Giveaway", f"end_{gid}")])
    rows.append([btn("🗑 Delete Giveaway", f"del_{gid}_ask")])
    rows.append([btn("⬅️ Back", "giveaways_list")])

    markup = kb(rows)
    if edit:
        edit_message(chat_id, edit, text, reply_markup=markup)
    else:
        send_message(chat_id, text, reply_markup=markup)


def render_winner_picker(chat_id, message_id, gid):
    g = get_giveaway(gid)
    participants = get_participants(gid)
    ranked = sorted(participants.items(), key=lambda kv: kv[1].get("points", 0), reverse=True)[:10]
    if not ranked:
        edit_message(chat_id, message_id, "📭 No participants to pick from yet.")
        return
    rows = []
    for uid, p in ranked:
        rows.append([btn(f"🎖 {uid} ({p.get('points', 0)} pts)", f"confirmwin_{gid}_{uid}")])
    rows.append([btn("⬅️ Back", f"manage_{gid}")])
    edit_message(chat_id, message_id, f"🎖 <b>Pick the winner for {esc(g['title'])}</b>", reply_markup=kb(rows))


def render_banned_list(chat_id, user_id, edit=None):
    banned = get_banned()
    if not banned:
        msg = "📭 No banned users."
        (edit_message(chat_id, edit, msg) if edit else send_message(chat_id, msg))
        return
    text = f"🚫 <b>{esc(cool_bold('Banned Users'))}</b>\n{DIVIDER}\n\n"
    rows = []
    for uid, info in banned.items():
        text += f"🆔 <code>{esc(uid)}</code>\n📝 {esc(info.get('reason', 'Not specified'))}\n\n"
        rows.append([btn(f"✅ Unban {uid}", f"unban_{uid}")])
    rows.append([btn("⬅️ Back", "giveaways_list")])
    markup = kb(rows)
    if edit:
        edit_message(chat_id, edit, text, reply_markup=markup)
    else:
        send_message(chat_id, text, reply_markup=markup)


# ==================== MESSAGE HANDLER ====================
def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")

    record_user_activity(message["from"])

    # Ban check comes before EVERYTHING else - a banned user gets nothing
    # from this bot, not even the join gate or the wizard.
    if is_banned(user_id):
        info = get_banned().get(str(user_id), {})
        send_message(
            chat_id,
            f"🚫 <b>You have been banned from using this bot.</b>\n\n"
            f"📝 Reason: {esc(info.get('reason', 'Not specified'))}\n\n"
            f"Contact {esc(DEVELOPER)} if you believe this is a mistake.",
        )
        return

    # Admin creation wizard takes priority over normal routing for admins mid-flow.
    if is_admin(user_id) and get_admin_wizard(user_id):
        if handle_wizard_text(message):
            return

    # Bot-wide force-join gate.
    missing = missing_joins(user_id)
    if missing:
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            args = parts[1].split() if len(parts) > 1 else []
            if args:
                set_json(f"pending_start:{user_id}", args)
        send_join_prompt(chat_id, missing)
        return

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        args = parts[1].split() if len(parts) > 1 else []
        if args and args[0].startswith("g"):
            payload = args[0][1:]
            if "_" in payload:
                gid, ref_id = payload.rsplit("_", 1)
                process_join_giveaway(chat_id, user_id, gid, referrer_id=ref_id)
                return
        send_welcome(chat_id, user_id)
        return

    if text.startswith("/giveaways"):
        render_giveaways_list(chat_id, user_id)
        return

    if text.startswith("/mystats"):
        handle_mystats(chat_id, user_id)
        return

    if text.startswith("/newgiveaway"):
        if not is_admin(user_id):
            send_message(chat_id, "❌ Admins only.")
            return
        start_new_giveaway_wizard(chat_id, user_id)
        return

    if text.startswith("/ban"):
        if not is_admin(user_id):
            send_message(chat_id, "❌ Admins only.")
            return
        parts = text.split(maxsplit=2)
        if len(parts) >= 3 and parts[1].isdigit():
            ban_user(parts[1], parts[2], user_id)
            send_message(chat_id, f"🚫 Banned <code>{esc(parts[1])}</code>.\nReason: {esc(parts[2])}")
            try:
                send_message(
                    int(parts[1]),
                    f"🚫 <b>You have been banned from using this bot.</b>\n\n"
                    f"📝 Reason: {esc(parts[2])}\n\n"
                    f"Contact {esc(DEVELOPER)} if you believe this is a mistake.",
                )
            except Exception:
                pass
        else:
            start_ban_wizard(chat_id, user_id)
        return

    if text.startswith("/unban"):
        if not is_admin(user_id):
            send_message(chat_id, "❌ Admins only.")
            return
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            unban_user(parts[1])
            send_message(chat_id, f"✅ Unbanned <code>{esc(parts[1])}</code>.")
        else:
            send_message(chat_id, "❌ Usage: /unban <user_id>")
        return

    if text.startswith("/banned"):
        if not is_admin(user_id):
            send_message(chat_id, "❌ Admins only.")
            return
        render_banned_list(chat_id, user_id)
        return

    if text.startswith("/cancel"):
        if get_admin_wizard(user_id):
            clear_admin_wizard(user_id)
            send_message(chat_id, "❌ Cancelled.")
        return


# ==================== CALLBACK HANDLER ====================
def handle_callback(callback):
    data = callback["data"]
    callback_id = callback["id"]
    user_id = callback["from"]["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]

    if is_banned(user_id):
        info = get_banned().get(str(user_id), {})
        answer_callback(
            callback_id,
            f"🚫 You're banned. Reason: {info.get('reason', 'Not specified')}",
            show_alert=True,
        )
        return

    if data != "checkjoin":
        missing = missing_joins(user_id)
        if missing:
            answer_callback(callback_id, "Please join the required channel(s) first.", show_alert=True)
            return

    if data == "checkjoin":
        missing = missing_joins(user_id)
        if missing:
            answer_callback(callback_id, "You haven't joined everything yet.", show_alert=True)
            return
        answer_callback(callback_id, "Access granted!")

        pending_start = get_json(f"pending_start:{user_id}", None)
        pending_join = get_json(f"pending_join:{user_id}", None)
        if pending_start:
            redis_del(f"pending_start:{user_id}")
            if pending_start and pending_start[0].startswith("g"):
                payload = pending_start[0][1:]
                if "_" in payload:
                    gid, ref_id = payload.rsplit("_", 1)
                    edit_message(chat_id, message_id, "✅ Verified! Loading...")
                    process_join_giveaway(chat_id, user_id, gid, referrer_id=ref_id)
                    return
            edit_message(chat_id, message_id, "✅ Verified!")
            send_welcome(chat_id, user_id)
        elif pending_join:
            redis_del(f"pending_join:{user_id}")
            edit_message(chat_id, message_id, "✅ Verified! Loading...")
            process_join_giveaway(chat_id, user_id, pending_join["gid"], referrer_id=pending_join.get("ref"), edit=None)
        else:
            edit_message(chat_id, message_id, "✅ You're all set! Send /start to begin.")
        return

    if data == "giveaways_list":
        answer_callback(callback_id)
        render_giveaways_list(chat_id, user_id, edit=message_id)
        return

    if data == "mystats":
        answer_callback(callback_id)
        handle_mystats(chat_id, user_id)
        return

    if data == "admin_panel":
        answer_callback(callback_id)
        if not is_admin(user_id):
            edit_message(chat_id, message_id, "❌ Admins only.")
            return
        render_giveaways_list(chat_id, user_id, edit=message_id)
        return

    if data == "newgiveaway":
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        start_new_giveaway_wizard(chat_id, user_id)
        return

    if data == "banwizard":
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        start_ban_wizard(chat_id, user_id)
        return

    if data == "bannedlist":
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        render_banned_list(chat_id, user_id, edit=message_id)
        return

    if data.startswith("unban_"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        target_id = data[6:]
        unban_user(target_id)
        render_banned_list(chat_id, user_id, edit=message_id)
        return

    if data.startswith("join_"):
        answer_callback(callback_id)
        gid = data[5:]
        process_join_giveaway(chat_id, user_id, gid, referrer_id=None, edit=message_id)
        return

    if data.startswith("lb_"):
        answer_callback(callback_id)
        gid = data[3:]
        handle_leaderboard(chat_id, gid, edit=None)
        return

    if data.startswith("manage_"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        gid = data[7:]
        render_manage_giveaway(chat_id, gid, edit=message_id)
        return

    if data.startswith("end_"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        gid = data[4:]
        giveaways = get_giveaways()
        if gid in giveaways:
            giveaways[gid]["status"] = "ended"
            save_giveaways(giveaways)
        render_manage_giveaway(chat_id, gid, edit=message_id)
        return

    if data.startswith("del_") and data.endswith("_ask"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        gid = data[4:-4]
        markup = kb([[btn("✅ Yes, delete", f"delyes_{gid}"), btn("❌ Cancel", f"manage_{gid}")]])
        edit_message(chat_id, message_id, "⚠️ Delete this giveaway and all its data? This can't be undone.", reply_markup=markup)
        return

    if data.startswith("delyes_"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        gid = data[7:]
        giveaways = get_giveaways()
        giveaways.pop(gid, None)
        save_giveaways(giveaways)
        redis_del(f"participants:{gid}")
        edit_message(chat_id, message_id, "✅ Giveaway deleted.")
        return

    if data.startswith("winner_"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        gid = data[7:]
        render_winner_picker(chat_id, message_id, gid)
        return

    if data.startswith("confirmwin_"):
        answer_callback(callback_id)
        if not is_admin(user_id):
            return
        _, gid, winner_uid = data.split("_", 2)
        giveaways = get_giveaways()
        g = giveaways.get(gid)
        if g:
            g.setdefault("winners", []).append(
                {"user_id": winner_uid, "confirmed_at": datetime.now().isoformat()}
            )
            save_giveaways(giveaways)
            try:
                send_message(
                    int(winner_uid),
                    f"🏆🎉 Congratulations! You've been confirmed as a winner of "
                    f"<b>{esc(g['title'])}</b>! The team will contact you soon.",
                )
            except Exception:
                pass
        edit_message(chat_id, message_id, f"✅ Winner confirmed: <code>{esc(winner_uid)}</code>")
        return


# ==================== WEBHOOK ROUTE ====================
@app.route("/api/index", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}

    if "message" in update:
        handle_message(update["message"])
    elif "callback_query" in update:
        handle_callback(update["callback_query"])
    elif "chat_join_request" in update:
        handle_join_request(update["chat_join_request"])

    return jsonify({"ok": True})


@app.route("/api/index", methods=["GET"])
def health():
    return jsonify({"status": "Referral giveaway bot is alive", "developer": DEVELOPER})
