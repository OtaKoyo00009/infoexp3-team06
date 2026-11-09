
async function loadMessages() {
    const r = await fetch('/api/messages');
    const xs = await r.json();

    document.querySelector('#messages').innerHTML = xs.map(x => `
        <article class="message" data-id="${x.id}">
            <b>${escapeHtml(x.name)}</b>
            <p class="message-text">${escapeHtml(x.message)}</p>
            <div class="meta">#${x.id}</div>
            <button type="button" class="edit-btn">編集</button>
            <button type="button" class="delete-btn">削除</button>
        </article>
    `).join('');
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
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
