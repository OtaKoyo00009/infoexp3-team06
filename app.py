
from flask import Flask, jsonify, render_template, request
from pathlib import Path
import sqlite3
import hashlib
import secrets
from datetime import datetime, timezone

app = Flask(__name__)
DB = Path("data/miniboard.db")

REACTION_KINDS = ("like", "correct", "wrong")


def connect():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            owner_token_hash TEXT
        )""")
        # 以前からあるDBにも投稿者認証用の列を追加する
        cols = [r["name"] for r in con.execute("PRAGMA table_info(messages)")]
        if "owner_token_hash" not in cols:
            con.execute("ALTER TABLE messages ADD COLUMN owner_token_hash TEXT")

        # 閲覧者のリアクション（いいね・正解した・間違えた）
        con.execute("""CREATE TABLE IF NOT EXISTS reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('like', 'correct', 'wrong')),
            created_at TEXT NOT NULL
        )""")
        # 既存DBに client_id 列がなければ追加（どのブラウザから押されたか）
        cols = [r["name"] for r in con.execute("PRAGMA table_info(reactions)")]
        if "client_id" not in cols:
            con.execute("ALTER TABLE reactions ADD COLUMN client_id TEXT")
        # いいね：1つの投稿につき1ブラウザ1回まで
        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_like
            ON reactions(message_id, client_id) WHERE kind = 'like'""")
        # 正解した／間違えた：1つの投稿につき1ブラウザでどちらか1回まで
        con.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uniq_answer
            ON reactions(message_id, client_id) WHERE kind IN ('correct', 'wrong')""")
        # 閲覧者のコメント
        con.execute("""CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def owner_status(con, message_id):
    """200: 正しい投稿者、403: 権限なし、404: 投稿なし"""
    row = con.execute(
        "SELECT owner_token_hash FROM messages WHERE id=?", (message_id,)
    ).fetchone()
    if row is None:
        return 404

    token = request.headers.get("X-Post-Token", "")
    stored_hash = row["owner_token_hash"]
    if not token or len(token) > 128 or not stored_hash:
        return 403
    return 200 if secrets.compare_digest(hash_token(token), stored_hash) else 403


def message_exists(con, message_id):
    row = con.execute("SELECT 1 FROM messages WHERE id=?", (message_id,)).fetchone()
    return row is not None


def reaction_counts(con, message_id):
    counts = {k: 0 for k in REACTION_KINDS}
    rows = con.execute(
        "SELECT kind, COUNT(*) AS n FROM reactions WHERE message_id=? GROUP BY kind",
        (message_id,),
    ).fetchall()
    for r in rows:
        counts[r["kind"]] = r["n"]
    return counts


def my_reactions(con, message_id, client_id):
    if not client_id:
        return []
    rows = con.execute(
        "SELECT kind FROM reactions WHERE message_id=? AND client_id=?",
        (message_id, client_id),
    ).fetchall()
    return [r["kind"] for r in rows]


def comments_of(con, message_id):
    rows = con.execute(
        "SELECT id, name, comment, created_at FROM comments WHERE message_id=? ORDER BY id",
        (message_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/messages")
def get_messages():
    client_id = request.args.get("client_id", "")
    with connect() as con:
        # 認証用ハッシュは絶対に公開しない
        rows = con.execute(
            "SELECT id, name, message, created_at FROM messages ORDER BY id DESC"
        ).fetchall()
        result = []
        for r in rows:
            m = dict(r)
            m["reactions"] = reaction_counts(con, r["id"])
            m["my_reactions"] = my_reactions(con, r["id"], client_id)
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

    if len(name) > 30:
        return jsonify({"error": "name is too long"}), 400

    if len(message) > 300:
        return jsonify({"error": "message is too long"}), 400

    # 秘密トークンは投稿ごとに生成し、DBにはハッシュだけ保存する
    owner_token = secrets.token_urlsafe(32)
    with connect() as con:
        cur = con.execute(
            """INSERT INTO messages(name, message, created_at, owner_token_hash)
               VALUES(?, ?, ?, ?)""",
            (name, message, now_iso(), hash_token(owner_token)),
        )
        row = con.execute(
            "SELECT id, name, message, created_at FROM messages WHERE id=?",
            (cur.lastrowid,),
        ).fetchone()

    # 生のトークンは投稿を作ったブラウザにこの1回だけ返す
    return jsonify({**dict(row), "owner_token": owner_token}), 201


@app.put("/api/messages/<int:message_id>")
def update_message(message_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    message = data.get("message", "")
    if not isinstance(message, str):
        return jsonify({"error": "message must be a string"}), 400

    message = message.strip()
    if not message:
        return jsonify({"error": "message is required"}), 400

    if len(message) > 300:
        return jsonify({"error": "message is too long"}), 400

    with connect() as con:
        status = owner_status(con, message_id)
        if status == 404:
            return jsonify({"error": "not found"}), 404
        if status == 403:
            return jsonify({"error": "forbidden"}), 403

        con.execute(
            "UPDATE messages SET message=? WHERE id=?", (message, message_id)
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

        con.execute("DELETE FROM messages WHERE id=?", (message_id,))
        # 投稿に紐づくリアクション・コメントも削除
        con.execute("DELETE FROM reactions WHERE message_id=?", (message_id,))
        con.execute("DELETE FROM comments WHERE message_id=?", (message_id,))
    return "", 204


# ---- 閲覧者向けAPI（既存機能を維持） ----

@app.post("/api/messages/<int:message_id>/reactions")
def add_reaction(message_id):
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "invalid JSON data"}), 400

    kind = data.get("kind")

    if kind not in REACTION_KINDS:
        return jsonify({"error": "kind must be like, correct or wrong"}), 400

    client_id = data.get("client_id", "")

    if not isinstance(client_id, str) or not (1 <= len(client_id) <= 64):
        return jsonify({"error": "client_id is required"}), 400

    with connect() as con:
        if not message_exists(con, message_id):
            return jsonify({"error": "not found"}), 404
        try:
            con.execute(
                "INSERT INTO reactions(message_id, kind, created_at, client_id) VALUES(?,?,?,?)",
                (message_id, kind, now_iso(), client_id),
            )
            status = 201
        except sqlite3.IntegrityError:
            # すでに押している（UNIQUE制約違反）
            status = 409
        body = {
            "reactions": reaction_counts(con, message_id),
            "my_reactions": my_reactions(con, message_id, client_id),
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

    if kind not in REACTION_KINDS:
        return jsonify({"error": "kind must be like, correct or wrong"}), 400

    client_id = data.get("client_id", "")

    if not isinstance(client_id, str) or not (1 <= len(client_id) <= 64):
        return jsonify({"error": "client_id is required"}), 400

    with connect() as con:
        if not message_exists(con, message_id):
            return jsonify({"error": "not found"}), 404
        # 自分（同じ client_id）が押したものだけ消す
        cur = con.execute(
            "DELETE FROM reactions WHERE message_id=? AND kind=? AND client_id=?",
            (message_id, kind, client_id),
        )
        body = {
            "reactions": reaction_counts(con, message_id),
            "my_reactions": my_reactions(con, message_id, client_id),
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

    if not isinstance(name, str):
        return jsonify({"error": "name must be a string"}), 400

    if not isinstance(comment, str):
        return jsonify({"error": "comment must be a string"}), 400

    name = name.strip()
    comment = comment.strip()

    if not name:
        return jsonify({"error": "name is required"}), 400

    if not comment:
        return jsonify({"error": "comment is required"}), 400

    if len(name) > 30:
        return jsonify({"error": "name is too long"}), 400

    if len(comment) > 200:
        return jsonify({"error": "comment is too long"}), 400

    with connect() as con:
        if not message_exists(con, message_id):
            return jsonify({"error": "not found"}), 404
        cur = con.execute(
            "INSERT INTO comments(message_id, name, comment, created_at) VALUES(?,?,?,?)",
            (message_id, name, comment, now_iso()),
        )
        row = con.execute("SELECT * FROM comments WHERE id=?", (cur.lastrowid,)).fetchone()

    return jsonify(dict(row)), 201


# flask run で起動した場合もテーブルが作られるよう、モジュール読み込み時に実行
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
