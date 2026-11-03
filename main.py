
import os
import sqlite3
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
DB = "tournament.db"


def database():
    return sqlite3.connect(DB)


def setup():
    with database() as db:
        db.execute("""
        CREATE TABLE IF NOT EXISTS players (
            chat INTEGER,
            uid INTEGER,
            username TEXT,
            name TEXT,
            PRIMARY KEY(chat, uid)
        )
        """)

        db.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat INTEGER,
            p1 INTEGER,
            p2 INTEGER,
            s1 INTEGER,
            s2 INTEGER,
            status TEXT DEFAULT 'pending'
        )
        """)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏆 LIVE TOURNAMENT BOT\n\n"
        "/register - тіркелу\n"
        "/result @username 3-1 - нәтиже жіберу\n"
        "/confirm ID - растау\n"
        "/reject ID - қабылдамау\n"
        "/table - рейтинг\n"
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user.username:
        await update.message.reply_text(
            "Алдымен Telegram username орнат!"
        )
        return

    with database() as db:
        db.execute("""
        INSERT OR REPLACE INTO players
        VALUES (?, ?, ?, ?)
        """, (chat.id, user.id, user.username.lower(), user.first_name))

    await update.message.reply_text(
        f"✅ {user.first_name} турнирге тіркелді!"
    )


async def result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if len(context.args) != 2:
        await update.message.reply_text(
            "Мысал: /result @dias 3-1"
        )
        return

    opponent = context.args[0].replace("@", "").lower()
    score = re.fullmatch(r"(\d{1,2})-(\d{1,2})", context.args[1])

    if not score:
        await update.message.reply_text("❌ Есеп форматы дұрыс емес!")
        return

    s1, s2 = map(int, score.groups())

    with database() as db:
        p1 = db.execute(
            "SELECT * FROM players WHERE chat=? AND uid=?",
            (chat.id, user.id)
        ).fetchone()

        p2 = db.execute(
            "SELECT * FROM players WHERE chat=? AND username=?",
            (chat.id, opponent)
        ).fetchone()

        if not p1 or not p2:
            await update.message.reply_text(
                "❌ Екі ойыншы да тіркелуі керек!"
            )
            return

        if user.id == p2[1]:
            await update.message.reply_text("Өзіңмен ойнай алмайсың!")
            return

        pending = db.execute("""
        SELECT id FROM matches
        WHERE chat=? AND status='pending'
        AND (
            (p1=? AND p2=?) OR (p1=? AND p2=?)
        )
        """, (chat.id, user.id, p2[1], p2[1], user.id)).fetchone()

        if pending:
            await update.message.reply_text(
                "Бұл матчтың растауын күтіп тұр!"
            )
            return

        cur = db.execute("""
        INSERT INTO matches (chat,p1,p2,s1,s2)
        VALUES (?,?,?,?,?)
        """, (chat.id, user.id, p2[1], s1, s2))

        match_id = cur.lastrowid

    await update.message.reply_text(
        f"⚽ MATCH #{match_id}\n\n"
        f"👤 {p1[3]} — {s1}:{s2} — {p2[3]}\n\n"
        f"⏳ Қарсылас растауы керек:\n"
        f"/confirm {match_id}\n"
        f"/reject {match_id}"
    )


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Мысал: /confirm 1")
        return

    mid = int(context.args[0])

    with database() as db:
        match = db.execute(
            "SELECT * FROM matches WHERE id=? AND chat=?",
            (mid, chat.id)
        ).fetchone()

        if not match or match[6] != "pending":
            await update.message.reply_text("❌ Матч табылмады!")
            return

        if user.id != match[2]:
            await update.message.reply_text(
                "❌ Тек қарсылас растай алады!"
            )
            return

        db.execute(
            "UPDATE matches SET status='confirmed' WHERE id=?",
            (mid,)
        )

    if match[4] > match[5]:
        winner = "1-ойыншы жеңді 🏆"
    elif match[4] < match[5]:
        winner = "2-ойыншы жеңді 🏆"
    else:
        winner = "Тең ойын 🤝"

    await update.message.reply_text(
        f"✅ MATCH #{mid} РАСТАЛДЫ!\n"
        f"⚽ Есеп: {match[4]}:{match[5]}\n"
        f"{winner}\n"
        f"📊 Рейтинг жаңартылды!"
    )


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Мысал: /reject 1")
        return

    mid = int(context.args[0])

    with database() as db:
        match = db.execute(
            "SELECT * FROM matches WHERE id=? AND chat=?",
            (mid, chat.id)
        ).fetchone()

        if not match or match[6] != "pending":
            await update.message.reply_text("Матч табылмады!")
            return

        if user.id != match[2]:
            await update.message.reply_text(
                "Тек қарсылас қабылдамауы мүмкін!"
            )
            return

        db.execute(
            "UPDATE matches SET status='rejected' WHERE id=?",
            (mid,)
        )

    await update.message.reply_text(
        "❌ Нәтиже қабылданбады!"
    )


async def table(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    with database() as db:
        players = db.execute(
            "SELECT * FROM players WHERE chat=?",
            (chat.id,)
        ).fetchall()

        matches = db.execute(
            "SELECT * FROM matches WHERE chat=? AND status='confirmed'",
            (chat.id,)
        ).fetchall()

    stats = {}

    for p in players:
        stats[p[1]] = {
            "name": p[3],
            "played": 0,
            "win": 0,
            "draw": 0,
            "loss": 0,
            "gf": 0,
            "ga": 0,
            "points": 0
        }

    for m in matches:
        a = stats[m[2]]
        b = stats[m[3]]

        a["played"] += 1
        b["played"] += 1

        a["gf"] += m[4]
        a["ga"] += m[5]
        b["gf"] += m[5]
        b["ga"] += m[4]

        if m[4] > m[5]:
            a["win"] += 1
            a["points"] += 3
            b["loss"] += 1

        elif m[4] < m[5]:
            b["win"] += 1
            b["points"] += 3
            a["loss"] += 1

        else:
            a["draw"] += 1
            b["draw"] += 1
            a["points"] += 1
            b["points"] += 1

    ranking = sorted(
        stats.values(),
        key=lambda x: (
            x["points"],
            x["gf"] - x["ga"],
            x["gf"]
        ),
        reverse=True
    )

    text = "🏆 LIVE TOURNAMENT TABLE\n"
    text += "━━━━━━━━━━━━━━\n"

    for i, p in enumerate(ranking, 1):
        text += (
            f"\n{i}. {p['name']}\n"
            f"⚽ Ойын: {p['played']}\n"
            f"🟢 Жеңіс: {p['win']}\n"
            f"🟡 Тең: {p['draw']}\n"
            f"🔴 Жеңіліс: {p['loss']}\n"
            f"🥅 Гол: {p['gf']}:{p['ga']}\n"
            f"🏅 Ұпай: {p['points']}\n"
        )

    await update.message.reply_text(text)


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN жоқ!")

    setup()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("result", result))
    app.add_handler(CommandHandler("confirm", confirm))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("table", table))

    print("BOT IS RUNNING!")
    app.run_polling()


if __name__ == "__main__":
    main()
