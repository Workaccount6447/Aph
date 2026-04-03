import logging
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)
from telegram.error import TelegramError
from database import Database
from config import (
    BOT_TOKEN, CHANNEL_USERNAME, CHANNEL_ID,
    REQUIRED_REFERRALS, ADMIN_IDS, OWNER_ID, FLASK_API_URL,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = Database()


# ═══════════════════════════════════════════════════════════
#  PERMISSION HELPERS
# ═══════════════════════════════════════════════════════════

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_admin(user_id: int) -> bool:
    """Admins + owner both pass this check."""
    return user_id == OWNER_ID or user_id in ADMIN_IDS


async def deny(update: Update, role: str = "admin"):
    role_text = "the owner" if role == "owner" else "an admin or owner"
    await update.message.reply_text(
        f"🚫 *Access Denied*\nThis command is restricted to {role_text} only.",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════
#  CHANNEL MEMBERSHIP HELPER
# ═══════════════════════════════════════════════════════════

async def is_channel_member(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in (
            ChatMember.MEMBER,
            ChatMember.ADMINISTRATOR,
            ChatMember.OWNER,
        )
    except TelegramError:
        return False


# ═══════════════════════════════════════════════════════════
#  KEYBOARDS
# ═══════════════════════════════════════════════════════════

def build_join_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")],
    ])


def build_referral_keyboard(bot_username: str, user_id: int) -> InlineKeyboardMarkup:
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔗 Share Referral Link",
            url=f"https://t.me/share/url?url={ref_link}&text=🎁%20Join%20this%20giveaway%20now!"
        )],
    ])


# ═══════════════════════════════════════════════════════════
#  /start  — PUBLIC (everyone can use)
# ═══════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referrer_id = int(args[0]) if args and args[0].isdigit() else None

    db.add_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        referrer_id=referrer_id if referrer_id and referrer_id != user.id else None,
    )

    # Force-join gate
    if not await is_channel_member(context.bot, user.id):
        await update.message.reply_text(
            "👋 Welcome to the *Giveaway Bot*!\n\n"
            "⚠️ You must *join our channel* before you can participate.\n"
            "Tap the button below, then press ✅ when done.",
            parse_mode="Markdown",
            reply_markup=build_join_keyboard(),
        )
        return

    await show_dashboard(update, context, user)


# ═══════════════════════════════════════════════════════════
#  DASHBOARD  (internal helper)
# ═══════════════════════════════════════════════════════════

async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE, user=None):
    user = user or update.effective_user
    bot_me = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start={user.id}"

    ref_count = db.get_referral_count(user.id)
    rank, total_users, top_count = db.get_rank(user.id)

    # Rank badge
    if rank == 1:
        rank_line = "🥇 *You are currently in 1st place — you're winning!*"
    elif rank == 2:
        rank_line = f"🥈 You're in *2nd place* — {top_count - ref_count} referral(s) behind the leader."
    elif rank == 3:
        rank_line = f"🥉 You're in *3rd place* — keep going!"
    else:
        rank_line = f"📍 You're ranked *#{rank}* out of {total_users} participants."

    # Progress bar capped at 10 blocks for visual
    bar_max = 10
    if top_count > 0:
        filled = round((ref_count / top_count) * bar_max)
    else:
        filled = bar_max if ref_count > 0 else 0
    bar = "🟢" * filled + "⚪️" * (bar_max - filled)

    text = (
        f"👋 Hello, *{user.full_name}*!\n\n"
        f"🎁 *Giveaway — Top Referrer Wins!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Your referrals: *{ref_count}*\n"
        f"Progress: {bar}\n"
        f"{rank_line}\n\n"
        f"🔗 *Your referral link:*\n`{ref_link}`\n\n"
        f"The person with the *most referrals* wins the prize!\n"
        f"Referrals only count after your friend *joins the channel*."
    )

    keyboard = build_referral_keyboard(bot_me.username, user.id)
    msg = update.message or update.callback_query.message
    await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ═══════════════════════════════════════════════════════════
#  CALLBACK: ✅ I've Joined button
# ═══════════════════════════════════════════════════════════

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if not await is_channel_member(context.bot, user.id):
        await query.answer("❌ You haven't joined yet! Please join first.", show_alert=True)
        return

    db.mark_channel_joined(user.id)

    referrer_id = db.get_referrer(user.id)
    if referrer_id:
        db.increment_referral(referrer_id)
        ref_count = db.get_referral_count(referrer_id)
        rank, total_users, top_count = db.get_rank(referrer_id)

        if rank == 1:
            rank_msg = f"🥇 *You are now in 1st place with {ref_count} referrals — you're currently winning!*"
        elif rank == 2:
            rank_msg = f"🥈 You're in 2nd place. {top_count - ref_count} more referral(s) to take the lead!"
        elif rank == 3:
            rank_msg = f"🥉 You're in 3rd place with {ref_count} referrals. Keep going!"
        else:
            rank_msg = f"📍 You're ranked #{rank} out of {total_users} with {ref_count} referrals."

        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    f"✅ *{user.full_name}* just joined via your referral link!\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{rank_msg}"
                ),
                parse_mode="Markdown",
            )
        except TelegramError:
            pass

    await query.message.delete()
    await show_dashboard(update, context, user)


# ═══════════════════════════════════════════════════════════
#  /all  — ADMIN + OWNER ONLY
#  Format: No. @username (referral_count)
# ═══════════════════════════════════════════════════════════

async def all_users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny(update)
        return

    all_users = db.get_all_users()

    if not all_users:
        await update.message.reply_text("📭 No participants yet.")
        return

    total = len(all_users)
    top_refs = all_users[0][3] if all_users else 0  # DB sorted DESC

    CHUNK = 50
    chunks = [all_users[i:i + CHUNK] for i in range(0, total, CHUNK)]

    for page_num, chunk in enumerate(chunks, 1):
        lines = []

        if page_num == 1:
            lines.append("👥 *All Participants*")
            lines.append(f"Total: *{total}* | 🏆 Leader has *{top_refs}* referrals")
            lines.append("━━━━━━━━━━━━━━━━━━━━━")

        for i, (uid, username, full_name, ref_count) in enumerate(chunk, (page_num - 1) * CHUNK + 1):
            if i == 1 and ref_count == top_refs and top_refs > 0:
                badge = "👑"
            elif i == 2:
                badge = "🥈"
            elif i == 3:
                badge = "🥉"
            else:
                badge = "▫️"
            name = f"@{username}" if username else full_name
            lines.append(f"{badge} {i}. {name} ({ref_count})")

        if len(chunks) > 1:
            lines.append(f"\n_Page {page_num} / {len(chunks)}_")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        await asyncio.sleep(0.3)


# ═══════════════════════════════════════════════════════════
#  /broadcast  — ADMIN + OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny(update)
        return

    if not context.args:
        await update.message.reply_text(
            "📢 *Usage:* `/broadcast <message>`\n"
            "_Example:_ `/broadcast Giveaway ends tomorrow!`",
            parse_mode="Markdown",
        )
        return

    message_text = " ".join(context.args)
    all_users = db.get_all_users()
    sent = failed = 0

    status_msg = await update.message.reply_text(
        f"📤 Sending to *{len(all_users)}* users...", parse_mode="Markdown"
    )

    for uid, *_ in all_users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 *Announcement*\n\n{message_text}",
                parse_mode="Markdown",
            )
            sent += 1
        except TelegramError:
            failed += 1
        await asyncio.sleep(0.05)  # Respect Telegram rate limits

    await status_msg.edit_text(
        f"✅ *Broadcast Complete*\n\n"
        f"📨 Sent: *{sent}*\n"
        f"❌ Failed: *{failed}*",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════
#  /listallpart  — ADMIN + OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def listallpart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny(update)
        return

    all_users = db.get_all_users()

    if not all_users:
        await update.message.reply_text("📭 No participants yet.")
        return

    total = len(all_users)
    eligible = [u for u in all_users if u[3] >= REQUIRED_REFERRALS]

    CHUNK = 30
    chunks = [all_users[i:i + CHUNK] for i in range(0, total, CHUNK)]

    for page_num, chunk in enumerate(chunks, 1):
        lines = []

        if page_num == 1:
            lines.append(f"👥 *Participant List* ({total} total)")
            lines.append(f"🏆 Eligible: *{len(eligible)}* | ⏳ Pending: *{total - len(eligible)}*")
            lines.append("━━━━━━━━━━━━━━━━━━━━━")

        for i, (uid, username, full_name, ref_count) in enumerate(chunk, (page_num - 1) * CHUNK + 1):
            if i == 1 and ref_count > 0:
                badge = "👑"
            elif i == 2:
                badge = "🥈"
            elif i == 3:
                badge = "🥉"
            else:
                badge = "▫️"
            uname_display = f"@{username}" if username else "—"
            lines.append(f"{badge} {i}. {full_name} | {uname_display} | {ref_count} refs")

        if len(chunks) > 1:
            lines.append(f"\n_Page {page_num} / {len(chunks)}_")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        await asyncio.sleep(0.3)


# ═══════════════════════════════════════════════════════════
#  /winners  — ADMIN + OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def winners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny(update)
        return

    all_users = db.get_all_users()
    # Filter users with at least 1 referral
    active = [(uid, uname, fname, refs) for uid, uname, fname, refs in all_users if refs > 0]

    if not active:
        await update.message.reply_text("😔 No referrals recorded yet.")
        return

    # #1 winner = highest referral count (first row — DB already sorts DESC)
    top_uid, top_uname, top_fname, top_refs = active[0]
    uname_display = f"@{top_uname}" if top_uname else "—"

    # Check for ties
    ties = [(uid, uname, fname, refs) for uid, uname, fname, refs in active if refs == top_refs]

    if len(ties) == 1:
        text = (
            f"🏆 *Current Giveaway Leader*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👑 *{top_fname}*\n"
            f"Username: {uname_display}\n"
            f"Referrals: *{top_refs}*\n"
            f"User ID: `{top_uid}`\n\n"
            f"_This person wins the prize when the giveaway ends._"
        )
    else:
        # Tie — list all tied users
        tie_lines = "\n".join(
            f"• {fname} | {'@' + uname if uname else '—'} | `{uid}`"
            for uid, uname, fname, refs in ties
        )
        text = (
            f"🏆 *Current Leaders — TIE!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"*{len(ties)} users* are tied at *{top_refs} referrals* each:\n\n"
            f"{tie_lines}\n\n"
            f"_The tie must be broken before the giveaway ends._"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════
#  /stats  — ADMIN + OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await deny(update)
        return

    all_users = db.get_all_users()
    total = len(all_users)
    active = [(uid, uname, fname, refs) for uid, uname, fname, refs in all_users if refs > 0]

    lines = [
        "📊 *Giveaway Stats*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"👥 Total Users: *{total}*",
        f"🎯 Active (1+ referrals): *{len(active)}*",
        f"😴 No referrals yet: *{total - len(active)}*",
        "",
        "🏅 *Top 3 Leaderboard:*",
    ]

    medals = ["👑", "🥈", "🥉"]
    if active:
        for i, (uid, uname, fname, refs) in enumerate(active[:3]):
            name = f"@{uname}" if uname else fname
            lines.append(f"{medals[i]} {name} — *{refs}* referrals")
    else:
        lines.append("_No referrals yet._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════
#  /addadmin  — OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await deny(update, role="owner")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("👤 *Usage:* `/addadmin <user_id>`", parse_mode="Markdown")
        return

    new_admin_id = int(context.args[0])
    if new_admin_id in ADMIN_IDS:
        await update.message.reply_text("ℹ️ This user is already an admin.")
        return

    ADMIN_IDS.append(new_admin_id)
    await update.message.reply_text(
        f"✅ User `{new_admin_id}` added as admin.", parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════
#  /removeadmin  — OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def removeadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await deny(update, role="owner")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("👤 *Usage:* `/removeadmin <user_id>`", parse_mode="Markdown")
        return

    target_id = int(context.args[0])
    if target_id not in ADMIN_IDS:
        await update.message.reply_text("ℹ️ This user is not an admin.")
        return

    ADMIN_IDS.remove(target_id)
    await update.message.reply_text(
        f"🗑️ User `{target_id}` removed from admins.", parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════
#  /admins  — OWNER ONLY
# ═══════════════════════════════════════════════════════════

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await deny(update, role="owner")
        return

    lines = [f"🔑 *Admin List*\n━━━━━━━━━━━━━━━━━━━━━", f"👑 Owner: `{OWNER_ID}`\n"]
    if ADMIN_IDS:
        for i, aid in enumerate(ADMIN_IDS, 1):
            lines.append(f"{i}. `{aid}`")
    else:
        lines.append("_No extra admins added yet._")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════
#  /math  — PUBLIC (everyone)
#  Calls the Flask math API and returns the answer
# ═══════════════════════════════════════════════════════════

async def math_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧮 *Math Solver*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "*Usage:* `/math <expression>`\n\n"
            "*Examples:*\n"
            "`/math 2 + 2`\n"
            "`/math sqrt(144)`\n"
            "`/math sin(pi / 2)`\n"
            "`/math 2^10`\n"
            "`/math factorial(10)`\n"
            "`/math log(e)`\n"
            "`/math round(3.14159, 2)`\n\n"
            "Supports: `+ - * / ** ^ sqrt log sin cos tan pi e` and more.",
            parse_mode="Markdown",
        )
        return

    expression = " ".join(context.args)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{FLASK_API_URL}/math",
                params={"q": expression},
            )
        data = resp.json()
    except httpx.RequestError:
        await update.message.reply_text(
            "⚠️ Math service is unavailable right now. Please try again later."
        )
        return

    if data.get("ok"):
        result = data["result"]
        await update.message.reply_text(
            f"🧮 *Math Result*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📥 Expression: `{expression}`\n"
            f"📤 Answer: `{result}`",
            parse_mode="Markdown",
        )
    else:
        error = data.get("error", "Unknown error")
        await update.message.reply_text(
            f"❌ *Error:* {error}\n\n"
            f"Use `/math` without arguments to see examples.",
            parse_mode="Markdown",
        )


# ═══════════════════════════════════════════════════════════
#  /help  — role-aware
# ═══════════════════════════════════════════════════════════

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if is_owner(uid):
        text = (
            "📖 *Commands — Owner*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👑 *Owner Only:*\n"
            "/addadmin `<id>` — Promote user to admin\n"
            "/removeadmin `<id>` — Demote an admin\n"
            "/admins — List all admins\n\n"
            "🔑 *Admin Commands:*\n"
            "/all — Numbered list: username (referrals)\n"
            "/listallpart — Full participant list\n"
            "/broadcast `<msg>` — Message all users\n"
            "/winners — Eligible participants\n"
            "/stats — Giveaway statistics\n\n"
            "👤 *User:*\n"
            "/start — Dashboard & referral link\n"
            "/math `<expression>` — Solve a math equation\n"
        )
    elif is_admin(uid):
        text = (
            "📖 *Commands — Admin*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🔑 *Admin Commands:*\n"
            "/all — Numbered list: username (referrals)\n"
            "/listallpart — Full participant list\n"
            "/broadcast `<msg>` — Message all users\n"
            "/winners — Eligible participants\n"
            "/stats — Giveaway statistics\n\n"
            "👤 *User:*\n"
            "/start — Dashboard & referral link\n"
            "/math `<expression>` — Solve a math equation\n"
        )
    else:
        # Regular users only see /start and /math
        text = (
            "📖 *Commands*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "/start — View your dashboard & referral link\n"
            "/math `<expression>` — Solve a math equation\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════
#  UNKNOWN COMMAND — silent for regular users
# ═══════════════════════════════════════════════════════════

async def unknown_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await update.message.reply_text("❓ Unknown command. Use /help to see available commands.")
    # Regular users get no response — no command info leaked


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ── Public ────────────────────────────────────────────
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("math", math_cmd))

    # ── Admin + Owner ─────────────────────────────────────
    app.add_handler(CommandHandler("all", all_users_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("listallpart", listallpart))
    app.add_handler(CommandHandler("winners", winners))
    app.add_handler(CommandHandler("stats", stats))

    # ── Owner only ────────────────────────────────────────
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("removeadmin", removeadmin))
    app.add_handler(CommandHandler("admins", list_admins))

    # ── Callbacks ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))

    # ── Fallback unknown commands ─────────────────────────
    app.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))

    logger.info("🤖 Bot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
