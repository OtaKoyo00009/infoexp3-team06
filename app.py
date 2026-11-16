

from flask import Flask, jsonify, render_template, request
from pathlib import Path
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone

app = Flask(__name__)
DB = Path("data/miniboard.db")

REACTION_KINDS = ("like", "correct", "wrong")


# ==============================
# データベース接続
# ==============================

def connect():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect() as con:

        # ------------------------------
        # 既存MiniBoard用テーブル
        # ------------------------------

        con.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            owner_token_hash TEXT
        )""")

        cols = [r["name"] for r in con.execute(
            "PRAGMA table_info(messages)"
        )]

        if "owner_token_hash" not in cols:
            con.execute(
                "ALTER TABLE messages ADD COLUMN owner_token_hash TEXT"
            )

        con.execute("""CREATE TABLE IF NOT EXISTS reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (
                kind IN ('like', 'correct', 'wrong')
            ),
            created_at TEXT NOT NULL
        )""")

        cols = [r["name"] for r in con.execute(
            "PRAGMA table_info(reactions)"
        )]

        if "client_id" not in cols:
            con.execute(
                "ALTER TABLE reactions ADD COLUMN client_id TEXT"
            )

        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_like
            ON reactions(message_id, client_id)
            WHERE kind = 'like'""")

        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_answer
            ON reactions(message_id, client_id)
            WHERE kind IN ('correct', 'wrong')""")

        con.execute("""CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")

        # ------------------------------
        # クイズ用テーブル
        # ------------------------------

        con.execute("""CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            created_at TEXT NOT NULL,
            owner_token_hash TEXT
        )""")

        con.execute("""CREATE TABLE IF NOT EXISTS quiz_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (
                kind IN ('like', 'correct', 'wrong')
            ),
            created_at TEXT NOT NULL,
            client_id TEXT
        )""")

        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_quiz_like
            ON quiz_reactions(quiz_id, client_id)
            WHERE kind = 'like'""")

        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_quiz_answer
            ON quiz_reactions(quiz_id, client_id)
            WHERE kind IN ('correct', 'wrong')""")

        con.execute("""CREATE TABLE IF NOT EXISTS quiz_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quiz_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")


# ==============================
# 共通関数
# ==============================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ==============================
# MiniBoard用補助関数
# ==============================

def owner_status(con, message_id):
    row = con.execute(
        "SELECT owner_token_hash FROM messages WHERE id=?",
        (message_id,)
    ).fetchone()

    if row is None:
        return 404

    token = request.headers.get("X-Post-Token", "")
    stored_hash = row["owner_token_hash"]

    if not token or len(token) > 128 or not stored_hash:
        return 403

    return 200 if secrets.compare_digest(
        hash_token(token), stored_hash
    ) else 403


def message_exists(con, message_id):
    row = con.execute(
        "SELECT 1 FROM messages WHERE id=?",
        (message_id,)
    ).fetchone()

    return row is not None


def reaction_counts(con, message_id):
    counts = {k: 0 for k in REACTION_KINDS}

    rows = con.execute(
        """SELECT kind, COUNT(*) AS n
           FROM reactions
           WHERE message_id=?
           GROUP BY kind""",
        (message_id,)
    ).fetchall()

    for r in rows:
        counts[r["kind"]] = r["n"]

    return counts


def my_reactions(con, message_id, client_id):
    if not client_id:
        return []

    rows = con.execute(
        """SELECT kind FROM reactions
           WHERE message_id=? AND client_id=?""",
        (message_id, client_id)
    ).fetchall()

    return [r["kind"] for r in rows]


def comments_of(con, message_id):
    rows = con.execute(
        """SELECT id, name, comment, created_at
           FROM comments
           WHERE message_id=?
           ORDER BY id""",
        (message_id,)
    ).fetchall()

    return [dict(r) for r in rows]


# ==============================
# クイズ用補助関数
# ==============================

def quiz_exists(con, quiz_id):
    row = con.execute(
        "SELECT 1 FROM quizzes WHERE id=?",
        (quiz_id,)
    ).fetchone()

    return row is not None


def quiz_owner_status(con, quiz_id):
    row = con.execute(
        "SELECT owner_token_hash FROM quizzes WHERE id=?",
        (quiz_id,)
    ).fetchone()

    if row is None:
        return 404

    token = request.headers.get("X-Post-Token", "")
    stored_hash = row["owner_token_hash"]

    if not token or len(token) > 128 or not stored_hash:
        return 403

    return 200 if secrets.compare_digest(
        hash_token(token), stored_hash
    ) else 403


def quiz_reaction_counts(con, quiz_id):
    counts = {k: 0 for k in REACTION_KINDS}

    rows = con.execute(
        """SELECT kind, COUNT(*) AS n
           FROM quiz_reactions
           WHERE quiz_id=?
           GROUP BY kind""",
        (quiz_id,)
    ).fetchall()

    for row in rows:
        counts[row["kind"]] = row["n"]

    return counts


def quiz_my_reactions(con, quiz_id, client_id):
    if not client_id:
        return []

    rows = con.execute(
        """SELECT kind FROM quiz_reactions
           WHERE quiz_id=? AND client_id=?""",
        (quiz_id, client_id)
    ).fetchall()

    return [row["kind"] for row in rows]


def quiz_comments_of(con, quiz_id):
    rows = con.execute(
        """SELECT id, name, comment, created_at
           FROM quiz_comments
           WHERE quiz_id=?
           ORDER BY id""",
        (quiz_id,)
    ).fetchall()

    return [dict(row) for row in rows]


# ==============================
# ページ表示
# ==============================

@app.get("/")
def index():
    return render_template("index.html")


# ==================================================
# 既存MiniBoard API
# ==================================================

@app.get("/api/messages")
def get_messages():
    client_id = request.args.get("client_id", "")

    with connect() as con:
        rows = con.execute(
            """SELECT id, name, message, created_at
               FROM messages
               ORDER BY id DESC"""
        ).fetchall()

        result = []

        for r in rows:
            m = dict(r)
            m["reactions"] = reaction_counts(con, r["id"])
            m["my_reactions"] = my_reactions(
                con, r["id"], client_id
            )
            m["comments"] = comments_of(con, r["id"])
            result.append(m)

    return jsonify(result)


@app.post("/api/messages")
def create_message():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    name = data.get("name", "")
    message = data.get("message", "")

    if not isinstance(name, str):
        return jsonify({"error": "name must be a string"}), 400

    if not isinstance(message, str):
        return jsonify({"error": "message must be a string"}), 400

    name = name.strip()
    message = message.strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    if not message:
        return jsonify({"error": "message is required"}), 400

    if len(name) > 30 or len(message) > 300:
        return jsonify({"error": "text is too long"}), 400

    owner_token = secrets.token_urlsafe(32)

    with connect() as con:
        cur = con.execute(
            """INSERT INTO messages
               (name, message, created_at, owner_token_hash)
               VALUES (?, ?, ?, ?)""",
            (name, message, now_iso(), hash_token(owner_token))
        )

        row = con.execute(
            """SELECT id, name, message, created_at
               FROM messages WHERE id=?""",
            (cur.lastrowid,)
        ).fetchone()

    return jsonify({
        **dict(row),
        "owner_token": owner_token
    }), 201


@app.put("/api/messages/<int:message_id>")
def update_message(message_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    message = data.get("message", "")

    if not isinstance(message, str):
        return jsonify({"error": "message must be a string"}), 400

    message = message.strip()

    if not message or len(message) > 300:
        return jsonify({"error": "invalid message"}), 400

    with connect() as con:
        status = owner_status(con, message_id)

        if status == 404:
            return jsonify({"error": "not found"}), 404

        if status == 403:
            return jsonify({"error": "forbidden"}), 403

        con.execute(
            "UPDATE messages SET message=? WHERE id=?",
            (message, message_id)
        )

    return jsonify({"ok": True})


@app.delete("/api/messages/<int:message_id>")
def delete_message(message_id):
    with connect() as con:
        status = owner_status(con, message_id)

        if status == 404:
            return jsonify({"error": "not found"}), 404

        if status == 403:
            return jsonify({"error": "forbidden"}), 403

        con.execute(
            "DELETE FROM messages WHERE id=?",
            (message_id,)
        )
        con.execute(
            "DELETE FROM reactions WHERE message_id=?",
            (message_id,)
        )
        con.execute(
            "DELETE FROM comments WHERE message_id=?",
            (message_id,)
        )

    return "", 204


@app.post("/api/messages/<int:message_id>/reactions")
def add_reaction(message_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    kind = data.get("kind")
    client_id = data.get("client_id", "")

    if kind not in REACTION_KINDS:
        return jsonify({"error": "invalid reaction kind"}), 400

    if not isinstance(client_id, str) or not (1 <= len(client_id) <= 64):
        return jsonify({"error": "client_id is required"}), 400

    with connect() as con:
        if not message_exists(con, message_id):
            return jsonify({"error": "not found"}), 404

        try:
            con.execute(
                """INSERT INTO reactions
                   (message_id, kind, created_at, client_id)
                   VALUES (?, ?, ?, ?)""",
                (message_id, kind, now_iso(), client_id)
            )
            status = 201

        except sqlite3.IntegrityError:
            status = 409

        body = {
            "reactions": reaction_counts(con, message_id),
            "my_reactions": my_reactions(
                con, message_id, client_id
            )
        }

    if status == 409:
        body["error"] = "already reacted"

    return jsonify(body), status


@app.delete("/api/messages/<int:message_id>/reactions")
def remove_reaction(message_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    kind = data.get("kind")
    client_id = data.get("client_id", "")

    if kind not in REACTION_KINDS:
        return jsonify({"error": "invalid reaction kind"}), 400

    if not isinstance(client_id, str) or not (1 <= len(client_id) <= 64):
        return jsonify({"error": "client_id is required"}), 400

    with connect() as con:
        if not message_exists(con, message_id):
            return jsonify({"error": "not found"}), 404

        cur = con.execute(
            """DELETE FROM reactions
               WHERE message_id=? AND kind=? AND client_id=?""",
            (message_id, kind, client_id)
        )

        body = {
            "reactions": reaction_counts(con, message_id),
            "my_reactions": my_reactions(
                con, message_id, client_id
            )
        }

    if cur.rowcount == 0:
        body["error"] = "not reacted"
        return jsonify(body), 404

    return jsonify(body), 200


@app.post("/api/messages/<int:message_id>/comments")
def add_comment(message_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    name = data.get("name", "")
    comment = data.get("comment", "")

    if not isinstance(name, str) or not isinstance(comment, str):
        return jsonify({"error": "invalid data"}), 400

    name = name.strip()
    comment = comment.strip()

    if not name or not comment:
        return jsonify({"error": "name and comment are required"}), 400

    if len(name) > 30 or len(comment) > 200:
        return jsonify({"error": "text is too long"}), 400

    with connect() as con:
        if not message_exists(con, message_id):
            return jsonify({"error": "not found"}), 404

        cur = con.execute(
            """INSERT INTO comments
               (message_id, name, comment, created_at)
               VALUES (?, ?, ?, ?)""",
            (message_id, name, comment, now_iso())
        )

        row = con.execute(
            "SELECT * FROM comments WHERE id=?",
            (cur.lastrowid,)
        ).fetchone()

    return jsonify(dict(row)), 201


# ==================================================
# クイズアプリ API
# ==================================================

@app.get("/api/quizzes")
def get_quizzes():
    client_id = request.args.get("client_id", "")

    with connect() as con:
        rows = con.execute(
            """SELECT id, name, question, answer, created_at
               FROM quizzes
               ORDER BY id DESC"""
        ).fetchall()

        result = []

        for row in rows:
            quiz = dict(row)
            quiz["reactions"] = quiz_reaction_counts(
                con, row["id"]
            )
            quiz["my_reactions"] = quiz_my_reactions(
                con, row["id"], client_id
            )
            quiz["comments"] = quiz_comments_of(
                con, row["id"]
            )
            result.append(quiz)

    return jsonify(result)


@app.post("/api/quizzes")
def create_quiz():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    name = data.get("name", "")
    question = data.get("question", "")
    answer = data.get("answer", "")

    if not all(isinstance(x, str) for x in (name, question, answer)):
        return jsonify({"error": "all fields must be strings"}), 400

    name = name.strip()
    question = question.strip()
    answer = answer.strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    if not question:
        return jsonify({"error": "question is required"}), 400

    if not answer:
        return jsonify({"error": "answer is required"}), 400

    if len(name) > 30:
        return jsonify({"error": "name is too long"}), 400

    if len(question) > 500:
        return jsonify({"error": "question is too long"}), 400

    if len(answer) > 300:
        return jsonify({"error": "answer is too long"}), 400

    owner_token = secrets.token_urlsafe(32)

    with connect() as con:
        cur = con.execute(
            """INSERT INTO quizzes
               (name, question, answer, created_at, owner_token_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (
                name,
                question,
                answer,
                now_iso(),
                hash_token(owner_token)
            )
        )

        row = con.execute(
            """SELECT id, name, question, answer, created_at
               FROM quizzes WHERE id=?""",
            (cur.lastrowid,)
        ).fetchone()

    return jsonify({
        **dict(row),
        "owner_token": owner_token
    }), 201


@app.put("/api/quizzes/<int:quiz_id>")
def update_quiz(quiz_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    question = data.get("question", "")
    answer = data.get("answer", "")

    if not isinstance(question, str) or not isinstance(answer, str):
        return jsonify({"error": "question and answer must be strings"}), 400

    question = question.strip()
    answer = answer.strip()

    if not question or not answer:
        return jsonify({"error": "question and answer are required"}), 400

    if len(question) > 500 or len(answer) > 300:
        return jsonify({"error": "text is too long"}), 400

    with connect() as con:
        status = quiz_owner_status(con, quiz_id)

        if status == 404:
            return jsonify({"error": "not found"}), 404

        if status == 403:
            return jsonify({"error": "forbidden"}), 403

        con.execute(
            """UPDATE quizzes
               SET question=?, answer=?
               WHERE id=?""",
            (question, answer, quiz_id)
        )

    return jsonify({"ok": True})


@app.delete("/api/quizzes/<int:quiz_id>")
def delete_quiz(quiz_id):
    with connect() as con:
        status = quiz_owner_status(con, quiz_id)

        if status == 404:
            return jsonify({"error": "not found"}), 404

        if status == 403:
            return jsonify({"error": "forbidden"}), 403

        con.execute(
            "DELETE FROM quiz_reactions WHERE quiz_id=?",
            (quiz_id,)
        )
        con.execute(
            "DELETE FROM quiz_comments WHERE quiz_id=?",
            (quiz_id,)
        )
        con.execute(
            "DELETE FROM quizzes WHERE id=?",
            (quiz_id,)
        )

    return "", 204


@app.post("/api/quizzes/<int:quiz_id>/reactions")
def add_quiz_reaction(quiz_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    kind = data.get("kind")
    client_id = data.get("client_id", "")

    if kind not in REACTION_KINDS:
        return jsonify({"error": "invalid reaction kind"}), 400

    if not isinstance(client_id, str) or not (1 <= len(client_id) <= 64):
        return jsonify({"error": "client_id is required"}), 400

    with connect() as con:
        if not quiz_exists(con, quiz_id):
            return jsonify({"error": "not found"}), 404

        try:
            con.execute(
                """INSERT INTO quiz_reactions
                   (quiz_id, kind, created_at, client_id)
                   VALUES (?, ?, ?, ?)""",
                (quiz_id, kind, now_iso(), client_id)
            )
            status = 201

        except sqlite3.IntegrityError:
            status = 409

        body = {
            "reactions": quiz_reaction_counts(con, quiz_id),
            "my_reactions": quiz_my_reactions(
                con, quiz_id, client_id
            )
        }

    if status == 409:
        body["error"] = "already reacted"

    return jsonify(body), status


@app.delete("/api/quizzes/<int:quiz_id>/reactions")
def remove_quiz_reaction(quiz_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    kind = data.get("kind")
    client_id = data.get("client_id", "")

    if kind not in REACTION_KINDS:
        return jsonify({"error": "invalid reaction kind"}), 400

    if not isinstance(client_id, str) or not (1 <= len(client_id) <= 64):
        return jsonify({"error": "client_id is required"}), 400

    with connect() as con:
        if not quiz_exists(con, quiz_id):
            return jsonify({"error": "not found"}), 404

        cur = con.execute(
            """DELETE FROM quiz_reactions
               WHERE quiz_id=? AND kind=? AND client_id=?""",
            (quiz_id, kind, client_id)
        )

        body = {
            "reactions": quiz_reaction_counts(con, quiz_id),
            "my_reactions": quiz_my_reactions(
                con, quiz_id, client_id
            )
        }

    if cur.rowcount == 0:
        body["error"] = "not reacted"
        return jsonify(body), 404

    return jsonify(body), 200


@app.post("/api/quizzes/<int:quiz_id>/comments")
def add_quiz_comment(quiz_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    name = data.get("name", "")
    comment = data.get("comment", "")

    if not isinstance(name, str) or not isinstance(comment, str):
        return jsonify({"error": "invalid data"}), 400

    name = name.strip()
    comment = comment.strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    if not comment:
        return jsonify({"error": "comment is required"}), 400

    if len(name) > 30 or len(comment) > 200:
        return jsonify({"error": "text is too long"}), 400

    with connect() as con:
        if not quiz_exists(con, quiz_id):
            return jsonify({"error": "not found"}), 404

        cur = con.execute(
            """INSERT INTO quiz_comments
               (quiz_id, name, comment, created_at)
               VALUES (?, ?, ?, ?)""",
            (quiz_id, name, comment, now_iso())
        )

        row = con.execute(
            "SELECT * FROM quiz_comments WHERE id=?",
            (cur.lastrowid,)
        ).fetchone()

    return jsonify(dict(row)), 201


# ==============================
# 起動時の初期化
# ==============================

init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )

