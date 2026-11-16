// ブラウザごとのID（リアクションの重複防止用）
function getClientId() {
    const KEY = 'miniboard-client-id';
    try {
        let id = localStorage.getItem(KEY);
        if (!id) {
            id = (crypto.randomUUID && crypto.randomUUID())
                || (Date.now().toString(36) + Math.random().toString(36).slice(2));
            localStorage.setItem(KEY, id);
        }
        return id;
    } catch {
        // localStorage が使えない環境ではページを開いている間だけのIDにする
        window._miniboardClientId ??= Date.now().toString(36) + Math.random().toString(36).slice(2);
        return window._miniboardClientId;
    }
}

const CLIENT_ID = getClientId();

// 押した状態に合わせてボタンを無効化・強調する
function applyReactionState(article, counts, mine) {
    for (const [kind, n] of Object.entries(counts)) {
        const span = article.querySelector(`.reaction-btn[data-kind="${kind}"] .count`);
        if (span) span.textContent = n;
    }

    const answered = mine.includes('correct') || mine.includes('wrong');

    // ※ disabled にするとダブルクリックを受け取れないので、クラスで状態を表す
    //   selected: 自分が押したボタン（ダブルクリックで取り消せる）
    //   locked  : 正解／間違いのもう片方（押せない）
    article.querySelectorAll('.reaction-btn').forEach(btn => {
        const kind = btn.dataset.kind;
        const pressed = mine.includes(kind);
        btn.classList.toggle('selected', pressed);
        btn.classList.toggle('locked', kind !== 'like' && answered && !pressed);
        btn.title = pressed ? 'ダブルクリックで取り消し' : '';
    });
}

async function loadMessages() {
    const r = await fetch(`/api/messages?client_id=${encodeURIComponent(CLIENT_ID)}`);
    const xs = await r.json();

    document.querySelector('#messages').innerHTML = xs.map(x => `
        <article class="message" data-id="${x.id}">
            <b>${escapeHtml(x.name)}</b>
            <p class="message-text">${escapeHtml(x.message)}</p>
            <div class="meta">#${x.id}</div>
            <button type="button" class="edit-btn">編集</button>
            <button type="button" class="delete-btn">削除</button>
            ${renderViewerPart(x)}
        </article>
    `).join('');
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

// 閲覧者パーツ（リアクションボタン・コメント欄）
function renderViewerPart(x) {
    const r = x.reactions ?? { like: 0, correct: 0, wrong: 0 };
    const mine = x.my_reactions ?? [];
    const comments = x.comments ?? [];
    const answered = mine.includes('correct') || mine.includes('wrong');

    // 押せるかどうか・押したかどうかの属性を作る
    const attrs = kind => {
        const pressed = mine.includes(kind);
        const locked = kind !== 'like' && answered && !pressed;
        const cls = 'reaction-btn' + (pressed ? ' selected' : '') + (locked ? ' locked' : '');
        const title = pressed ? ' title="ダブルクリックで取り消し"' : '';
        return `class="${cls}" data-kind="${kind}"${title}`;
    };

    return `
        <div class="reactions">
            <button type="button" ${attrs('like')}>👍 いいね <span class="count">${r.like}</span></button>
            <button type="button" ${attrs('correct')}>⭕ 正解した <span class="count">${r.correct}</span></button>
            <button type="button" ${attrs('wrong')}>❌ 間違えた <span class="count">${r.wrong}</span></button>
        </div>
        <section class="comments">
            <div class="comments-title">コメント (${comments.length})</div>
            <ul class="comment-list">
                ${comments.map(c => `<li><b>${escapeHtml(c.name)}</b>：${escapeHtml(c.comment)}</li>`).join('')}
            </ul>
            <form class="comment-form">
                <input class="comment-name" maxlength="30" placeholder="Nickname" required>
                <input class="comment-text" maxlength="200" placeholder="コメントを書く" required>
                <button>コメントする</button>
            </form>
        </section>
    `;
}

// 投稿の編集
document.querySelector('#messages').addEventListener('click', e => {
    if (!e.target.matches('.edit-btn')) return;

    const article = e.target.closest('.message');
    const id = article.dataset.id;
    const text = article.querySelector('.message-text');
    const editBtn = e.target;

    // 元のメッセージを編集欄に表示
    const editor = document.createElement('textarea');
    editor.value = text.textContent;
    editor.maxLength = 300;

    // 保存・キャンセルボタン
    const saveBtn = document.createElement('button');
    saveBtn.textContent = '保存';
    saveBtn.type = 'button';
    saveBtn.className = 'save-btn';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'キャンセル';
    cancelBtn.type = 'button';
    cancelBtn.className = 'cancel-btn';

    // 表示を編集モードへ切り替える
    text.replaceWith(editor);
    editBtn.replaceWith(saveBtn);
    saveBtn.after(cancelBtn);
    editor.focus();

    // キャンセル
    cancelBtn.addEventListener('click', () => {
        editor.replaceWith(text);
        saveBtn.replaceWith(editBtn);
        cancelBtn.remove();
    });

    // 保存
    saveBtn.addEventListener('click', async () => {
        const message = editor.value.trim();

        if (!message) {
            alert('メッセージを入力してください');
            return;
        }

        saveBtn.disabled = true;

        try {
            const r = await fetch(`/api/messages/${id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ message })
            });

            if (!r.ok) {
                throw new Error(`HTTP ${r.status}`);
            }

            document.querySelector('#status').textContent =
                '投稿を編集しました';

            await loadMessages();
        } catch (error) {
            console.error(error);
            document.querySelector('#status').textContent =
                '編集に失敗しました';
            saveBtn.disabled = false;
        }
    });
});

// 投稿の削除
document.querySelector('#messages').addEventListener('click', async e => {
    if (!e.target.matches('.delete-btn')) return;

    const article = e.target.closest('.message');
    const id = article.dataset.id;
    const deleteBtn = e.target;

    if (!confirm('この投稿を削除しますか？')) return;

    deleteBtn.disabled = true;

    try {
        const r = await fetch(`/api/messages/${id}`, {
            method: 'DELETE'
        });

        if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
        }

        document.querySelector('#status').textContent =
            '投稿を削除しました';

        await loadMessages();
    } catch (error) {
        console.error(error);
        document.querySelector('#status').textContent =
            '削除に失敗しました';
        deleteBtn.disabled = false;
    }
});

// リアクションをサーバーへ送る（method: 'POST' で押す / 'DELETE' で取り消す）
async function sendReaction(btn, method) {
    const article = btn.closest('.message');
    const id = article.dataset.id;
    const kind = btn.dataset.kind;

    // 送信中の連打を防ぐ（正解・間違いは両方とも止める）
    const lockTargets = kind === 'like'
        ? [btn]
        : [...article.querySelectorAll('.reaction-btn[data-kind="correct"], .reaction-btn[data-kind="wrong"]')];
    lockTargets.forEach(b => { b.disabled = true; });

    try {
        const r = await fetch(`/api/messages/${id}/reactions`, {
            method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ kind, client_id: CLIENT_ID })
        });

        // POST   201: 押せた     / 409: すでに押していた
        // DELETE 200: 取り消せた / 404: 押していなかった
        // いずれもサーバーの最新状態が返ってくるので、それを画面に反映する
        const okStatuses = method === 'POST' ? [201, 409] : [200, 404];
        if (!okStatuses.includes(r.status)) {
            throw new Error(`HTTP ${r.status}`);
        }

        const data = await r.json();
        if (!data.reactions) {
            // 投稿自体が見つからない（削除済みなど）
            await loadMessages();
            return;
        }
        applyReactionState(article, data.reactions, data.my_reactions);

        if (method === 'POST' && r.status === 409) {
            document.querySelector('#status').textContent =
                'この投稿にはすでにリアクションしています';
        }
        if (method === 'DELETE' && r.status === 200) {
            document.querySelector('#status').textContent =
                'リアクションを取り消しました';
        }
    } catch (error) {
        console.error(error);
        document.querySelector('#status').textContent =
            method === 'POST' ? 'リアクションに失敗しました' : '取り消しに失敗しました';
    } finally {
        lockTargets.forEach(b => { b.disabled = false; });
    }
}

// クリック：まだ押していないボタンを押す
document.querySelector('#messages').addEventListener('click', e => {
    // ボタン内の <span> をクリックしても拾えるよう closest を使う
    const btn = e.target.closest('.reaction-btn');
    if (!btn || btn.disabled) return;

    // ダブルクリックの1回目の時点で「押した状態」だったかを記録しておく
    // （未押下のボタンをダブルクリックしたとき、押す→即取り消し にならないように）
    if (e.detail <= 1) {
        btn.dataset.armed = btn.classList.contains('selected') ? '1' : '';
    }

    // ダブルクリックの2回目のクリックは無視
    if (e.detail > 1) return;

    if (btn.classList.contains('selected') || btn.classList.contains('locked')) return;

    sendReaction(btn, 'POST');
});

// ダブルクリック：押したボタンを取り消す
document.querySelector('#messages').addEventListener('dblclick', e => {
    const btn = e.target.closest('.reaction-btn');
    if (!btn || btn.disabled) return;

    if (btn.dataset.armed !== '1' || !btn.classList.contains('selected')) return;
    btn.dataset.armed = '';

    sendReaction(btn, 'DELETE');
});

// コメント投稿
document.querySelector('#messages').addEventListener('submit', async e => {
    if (!e.target.matches('.comment-form')) return;
    e.preventDefault();

    const form = e.target;
    const id = form.closest('.message').dataset.id;
    const name = form.querySelector('.comment-name').value;
    const comment = form.querySelector('.comment-text').value;
    const submitBtn = form.querySelector('button');

    submitBtn.disabled = true;

    try {
        const r = await fetch(`/api/messages/${id}/comments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, comment })
        });

        if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
        }

        document.querySelector('#status').textContent =
            'コメントしました';

        await loadMessages();
    } catch (error) {
        console.error(error);
        document.querySelector('#status').textContent =
            'コメントに失敗しました';
        submitBtn.disabled = false;
    }
});

// 新規投稿（既存の機能）
document.querySelector('#form').addEventListener('submit', async e => {
    e.preventDefault();

    const name = document.querySelector('#name').value;
    const message = document.querySelector('#message').value;

    const r = await fetch('/api/messages', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name, message })
    });

    document.querySelector('#status').textContent =
        r.ok ? '投稿しました' : '投稿に失敗しました';

    if (r.ok) {
        document.querySelector('#message').value = '';
        await loadMessages();
    }
});

loadMessages();