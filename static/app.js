

// ========================================
// ブラウザごとのID（リアクションの重複防止用）
// ========================================

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
        window._miniboardClientId ??=
            Date.now().toString(36) + Math.random().toString(36).slice(2);

        return window._miniboardClientId;
    }
}

const CLIENT_ID = getClientId();


// ========================================
// 投稿者本人の編集・削除用トークン
// ========================================

function postTokenKey(id) {
    return `miniboard-post-token-${id}`;
}

function getPostToken(id) {
    try {
        return localStorage.getItem(postTokenKey(id)) || '';
    } catch {
        return '';
    }
}

function savePostToken(id, token) {
    try {
        localStorage.setItem(postTokenKey(id), token);
        return true;
    } catch {
        return false;
    }
}

function removePostToken(id) {
    try {
        localStorage.removeItem(postTokenKey(id));
    } catch {
        // 保存できない場合は何もしない
    }
}


// ========================================
// 共通処理
// ========================================

function escapeHtml(value) {
    const d = document.createElement('div');
    d.textContent = String(value ?? '');
    return d.innerHTML;
}


// ========================================
// 難易度の計算
// ========================================

// 正答率（0〜1）
function correctRate(reactions) {
    const correct = reactions?.correct ?? 0;
    const wrong = reactions?.wrong ?? 0;
    const total = correct + wrong;

    return total === 0 ? null : correct / total;
}

// 回答者数
function answerCount(reactions) {
    return (reactions?.correct ?? 0) + (reactions?.wrong ?? 0);
}

// 難易度の表示
function renderDifficulty(reactions) {
    const rate = correctRate(reactions);

    if (rate === null) {
        return '<span class="level level-none">難易度 −</span> まだ回答がありません';
    }

    const total = answerCount(reactions);
    const correct = reactions.correct ?? 0;
    const pct = Math.round(rate * 100);

    const [label, cls] =
        rate >= 0.7 ? ['かんたん', 'easy'] :
        rate >= 0.4 ? ['ふつう', 'normal'] :
        ['むずかしい', 'hard'];

    return `
        <span class="level level-${cls}">${label}</span>
        正答率 ${pct}%（${total}人中${correct}人正解）
    `;
}


// ========================================
// クイズの並べ替え
// ========================================

// new  : 新しい順
// old  : 古い順
// hard : 難しい順
// easy : 簡単な順

function sortQuizzes(quizzes, mode) {
    const arr = [...quizzes];

    const byNew = (a, b) => b.id - a.id;

    if (mode === 'old') {
        return arr.sort((a, b) => a.id - b.id);
    }

    if (mode !== 'hard' && mode !== 'easy') {
        return arr.sort(byNew);
    }

    return arr.sort((a, b) => {
        const ra = correctRate(a.reactions);
        const rb = correctRate(b.reactions);

        // 回答がないクイズは最後にする
        if (ra === null && rb === null) return byNew(a, b);
        if (ra === null) return 1;
        if (rb === null) return -1;

        // 正答率で比較
        if (ra !== rb) {
            return mode === 'hard' ? ra - rb : rb - ra;
        }

        // 正答率が同じなら回答者数が多い方を先にする
        const diff = answerCount(b.reactions) - answerCount(a.reactions);

        return diff !== 0 ? diff : byNew(a, b);
    });
}


// ========================================
// クイズ一覧の取得・表示
// ========================================

async function loadQuizzes() {
    try {
        const r = await fetch(
            `/api/quizzes?client_id=${encodeURIComponent(CLIENT_ID)}`
        );

        if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
        }

        const quizzes = await r.json();

        const sortSelect = document.querySelector('#sort');
        const mode = sortSelect ? sortSelect.value : 'new';

        const sorted = sortQuizzes(quizzes, mode);

        document.querySelector('#quizzes').innerHTML =
            sorted.map(q => `
                <article class="quiz" data-id="${q.id}">

                    <b>${escapeHtml(q.name)}</b>

                    <p class="question">
                        ${escapeHtml(q.question)}
                    </p>

                    <p class="answer" hidden>
                        解答：${escapeHtml(q.answer)}
                    </p>

                    <button type="button" class="answer-btn">
                        解答を見る
                    </button>

                    <div class="meta">#${q.id}</div>

                    ${getPostToken(q.id) ? `
                        <button type="button" class="edit-btn">編集</button>
                        <button type="button" class="delete-btn">削除</button>
                    ` : ''}

                    ${renderViewerPart(q)}

                </article>
            `).join('');

    } catch (error) {
        console.error(error);

        document.querySelector('#status').textContent =
            'クイズの読み込みに失敗しました';
    }
}


// ========================================
// リアクション・コメント欄の表示
// ========================================

function renderViewerPart(q) {
    const reactions = q.reactions ?? {
        like: 0,
        correct: 0,
        wrong: 0
    };

    const mine = q.my_reactions ?? [];
    const comments = q.comments ?? [];

    const answered =
        mine.includes('correct') || mine.includes('wrong');

    const attrs = kind => {
        const pressed = mine.includes(kind);
        const locked = kind !== 'like' && answered && !pressed;

        const cls =
            'reaction-btn'
            + (pressed ? ' selected' : '')
            + (locked ? ' locked' : '');

        const title = pressed
            ? ' title="ダブルクリックで取り消し"'
            : '';

        return `class="${cls}" data-kind="${kind}"${title}`;
    };

    return `
        <div class="difficulty">
            ${renderDifficulty(reactions)}
        </div>

        <div class="reactions">
            <button type="button" ${attrs('like')}>
                👍 いいね
                <span class="count">${reactions.like}</span>
            </button>

            <button type="button" ${attrs('correct')}>
                ⭕ 正解した
                <span class="count">${reactions.correct}</span>
            </button>

            <button type="button" ${attrs('wrong')}>
                ❌ 間違えた
                <span class="count">${reactions.wrong}</span>
            </button>
        </div>

        <section class="comments">
            <div class="comments-title">
                コメント (${comments.length})
            </div>

            <ul class="comment-list">
                ${comments.map(c => `
                    <li>
                        <b>${escapeHtml(c.name)}</b>：
                        ${escapeHtml(c.comment)}
                    </li>
                `).join('')}
            </ul>

            <form class="comment-form">
                <input
                    class="comment-name"
                    maxlength="30"
                    placeholder="Nickname"
                    required
                >

                <input
                    class="comment-text"
                    maxlength="200"
                    placeholder="コメントを書く"
                    required
                >

                <button type="submit">コメントする</button>
            </form>
        </section>
    `;
}


// ========================================
// 解答の表示・非表示
// ========================================

document.querySelector('#quizzes').addEventListener('click', e => {
    if (!e.target.matches('.answer-btn')) return;

    const article = e.target.closest('.quiz');
    const answer = article.querySelector('.answer');

    answer.hidden = !answer.hidden;

    e.target.textContent =
        answer.hidden ? '解答を見る' : '解答を隠す';
});


// ========================================
// クイズの編集
// ========================================

document.querySelector('#quizzes').addEventListener('click', e => {
    if (!e.target.matches('.edit-btn')) return;

    const article = e.target.closest('.quiz');
    const id = article.dataset.id;

    const question = article.querySelector('.question');
    const answer = article.querySelector('.answer');
    const editBtn = e.target;

    const questionEditor = document.createElement('textarea');
    questionEditor.value = question.textContent.trim();
    questionEditor.maxLength = 300;

    const answerEditor = document.createElement('textarea');
    answerEditor.value = answer.textContent
        .replace(/^解答：/, '')
        .trim();
    answerEditor.maxLength = 300;

    const saveBtn = document.createElement('button');
    saveBtn.textContent = '保存';
    saveBtn.type = 'button';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'キャンセル';
    cancelBtn.type = 'button';

    question.replaceWith(questionEditor);
    answer.replaceWith(answerEditor);
    editBtn.replaceWith(saveBtn);
    saveBtn.after(cancelBtn);

    questionEditor.focus();

    // キャンセル
    cancelBtn.addEventListener('click', () => {
        questionEditor.replaceWith(question);
        answerEditor.replaceWith(answer);
        saveBtn.replaceWith(editBtn);
        cancelBtn.remove();
    });

    // 保存
    saveBtn.addEventListener('click', async () => {
        const newQuestion = questionEditor.value.trim();
        const newAnswer = answerEditor.value.trim();

        if (!newQuestion || !newAnswer) {
            alert('問題文と解答を入力してください');
            return;
        }

        saveBtn.disabled = true;

        try {
            const r = await fetch(`/api/quizzes/${id}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Post-Token': getPostToken(id)
                },
                body: JSON.stringify({
                    question: newQuestion,
                    answer: newAnswer
                })
            });

            if (!r.ok) {
                throw new Error(`HTTP ${r.status}`);
            }

            document.querySelector('#status').textContent =
                'クイズを編集しました';

            await loadQuizzes();

        } catch (error) {
            console.error(error);

            document.querySelector('#status').textContent =
                '編集に失敗しました';

            saveBtn.disabled = false;
        }
    });
});


// ========================================
// クイズの削除
// ========================================

document.querySelector('#quizzes').addEventListener('click', async e => {
    if (!e.target.matches('.delete-btn')) return;

    const article = e.target.closest('.quiz');
    const id = article.dataset.id;
    const deleteBtn = e.target;

    if (!confirm('このクイズを削除しますか？')) return;

    deleteBtn.disabled = true;

    try {
        const r = await fetch(`/api/quizzes/${id}`, {
            method: 'DELETE',
            headers: {
                'X-Post-Token': getPostToken(id)
            }
        });

        if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
        }

        removePostToken(id);

        document.querySelector('#status').textContent =
            'クイズを削除しました';

        await loadQuizzes();

    } catch (error) {
        console.error(error);

        document.querySelector('#status').textContent =
            '削除に失敗しました';

        deleteBtn.disabled = false;
    }
});


// ========================================
// リアクション状態の更新
// ========================================

function applyReactionState(article, counts, mine) {
    for (const [kind, n] of Object.entries(counts)) {
        const span = article.querySelector(
            `.reaction-btn[data-kind="${kind}"] .count`
        );

        if (span) span.textContent = n;
    }

    // 難易度の表示を更新
    const difficulty = article.querySelector('.difficulty');

    if (difficulty) {
        difficulty.innerHTML = renderDifficulty(counts);
    }

    const answered =
        mine.includes('correct') || mine.includes('wrong');

    article.querySelectorAll('.reaction-btn').forEach(btn => {
        const kind = btn.dataset.kind;
        const pressed = mine.includes(kind);

        btn.classList.toggle('selected', pressed);

        btn.classList.toggle(
            'locked',
            kind !== 'like' && answered && !pressed
        );

        btn.title = pressed ? 'ダブルクリックで取り消し' : '';
    });
}


// ========================================
// リアクションの送信・取り消し
// ========================================

async function sendReaction(btn, method) {
    const article = btn.closest('.quiz');
    const id = article.dataset.id;
    const kind = btn.dataset.kind;

    const lockTargets = kind === 'like'
        ? [btn]
        : [
            ...article.querySelectorAll(
                '.reaction-btn[data-kind="correct"], .reaction-btn[data-kind="wrong"]'
            )
        ];

    lockTargets.forEach(b => {
        b.disabled = true;
    });

    try {
        const r = await fetch(`/api/quizzes/${id}/reactions`, {
            method,
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                kind,
                client_id: CLIENT_ID
            })
        });

        const okStatuses = method === 'POST'
            ? [201, 409]
            : [200, 404];

        if (!okStatuses.includes(r.status)) {
            throw new Error(`HTTP ${r.status}`);
        }

        const data = await r.json();

        if (!data.reactions) {
            await loadQuizzes();
            return;
        }

        applyReactionState(
            article,
            data.reactions,
            data.my_reactions
        );

        if (method === 'POST' && r.status === 409) {
            document.querySelector('#status').textContent =
                'このクイズにはすでにリアクションしています';
        }

        if (method === 'DELETE' && r.status === 200) {
            document.querySelector('#status').textContent =
                'リアクションを取り消しました';
        }

    } catch (error) {
        console.error(error);

        document.querySelector('#status').textContent =
            method === 'POST'
                ? 'リアクションに失敗しました'
                : '取り消しに失敗しました';

    } finally {
        lockTargets.forEach(b => {
            b.disabled = false;
        });
    }
}


// クリック：まだ押していないボタンを押す

document.querySelector('#quizzes').addEventListener('click', e => {
    const btn = e.target.closest('.reaction-btn');

    if (!btn || btn.disabled) return;

    if (e.detail <= 1) {
        btn.dataset.armed =
            btn.classList.contains('selected') ? '1' : '';
    }

    if (e.detail > 1) return;

    if (
        btn.classList.contains('selected') ||
        btn.classList.contains('locked')
    ) {
        return;
    }

    sendReaction(btn, 'POST');
});


// ダブルクリック：押したリアクションを取り消す

document.querySelector('#quizzes').addEventListener('dblclick', e => {
    const btn = e.target.closest('.reaction-btn');

    if (!btn || btn.disabled) return;

    if (
        btn.dataset.armed !== '1' ||
        !btn.classList.contains('selected')
    ) {
        return;
    }

    btn.dataset.armed = '';

    sendReaction(btn, 'DELETE');
});


// ========================================
// コメント投稿
// ========================================

document.querySelector('#quizzes').addEventListener('submit', async e => {
    if (!e.target.matches('.comment-form')) return;

    e.preventDefault();

    const form = e.target;
    const id = form.closest('.quiz').dataset.id;

    const name = form.querySelector('.comment-name').value.trim();
    const comment = form.querySelector('.comment-text').value.trim();
    const submitBtn = form.querySelector('button');

    if (!name || !comment) return;

    submitBtn.disabled = true;

    try {
        const r = await fetch(`/api/quizzes/${id}/comments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name,
                comment
            })
        });

        if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
        }

        document.querySelector('#status').textContent =
            'コメントしました';

        await loadQuizzes();

    } catch (error) {
        console.error(error);

        document.querySelector('#status').textContent =
            'コメントに失敗しました';

        submitBtn.disabled = false;
    }
});


// ========================================
// 並べ替え
// ========================================

document.querySelector('#sort').addEventListener('change', () => {
    loadQuizzes();
});


// ========================================
// 新しいクイズの投稿
// ========================================

document.querySelector('#form').addEventListener('submit', async e => {
    e.preventDefault();

    const name = document.querySelector('#name').value.trim();
    const question = document.querySelector('#question').value.trim();
    const answer = document.querySelector('#answer').value.trim();

    const status = document.querySelector('#status');

    if (!name || !question || !answer) {
        status.textContent =
            '名前・問題文・解答をすべて入力してください';
        return;
    }

    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    try {
        const r = await fetch('/api/quizzes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name,
                question,
                answer
            })
        });

        if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
        }

        const created = await r.json();

        // 投稿者用トークンを保存
        const saved = created.owner_token
            ? savePostToken(created.id, created.owner_token)
            : false;

        status.textContent = saved
            ? 'クイズを投稿しました'
            : 'クイズを投稿しました（編集・削除用トークンを取得できませんでした）';

        document.querySelector('#form').reset();

        await loadQuizzes();

    } catch (error) {
        console.error(error);

        status.textContent = 'クイズの投稿に失敗しました';

    } finally {
        submitBtn.disabled = false;
    }
});


// ========================================
// 初期表示
// ========================================

loadQuizzes();

