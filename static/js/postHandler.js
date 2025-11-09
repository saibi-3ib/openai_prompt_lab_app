// --- postHandler.js (updated) ---
// Responsibilities:
// - renderPostList: render posts returned from server (server-side or API)
// - initPostHandler: wire up event handlers (selection, filtering, batch analysis)
// - Delegated handling for .ticker-btn and ticker-tag removal
// - Auto-trigger filtering on inputs with debounce

// --- ヘルパー / ユーティリティ ---
function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/"/g, '&quot;')
              .replace(/'/g, '&#39;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/\n/g, '&#10;');
}

function debounce(fn, wait) {
    let t;
    return function(...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), wait);
    };
}

// run ボタンをクリックする代わりに、filter 発火を一元化する
function triggerFilter() {
    const runBtn = elements?.filter?.runBtn || document.getElementById('filter-run-btn');
    if (runBtn) runBtn.click();
}
const triggerFilterDebounced = debounce(() => triggerFilter(), 250);

/**
 * addTickerTag:
 * 既存の ticker-tag と見た目・構造を揃えてタグを追加する。
 * 重複は無視する。追加に成功したら true を返す。
 * - 正規化は大文字に統一して重複を防ぐ（AAPL == aapl）。
 * - 新しいタグは先頭に挿入して左側に表示されるようにする。
 */
function addTickerTag(ticker) {
    if (!ticker) return false;
    const tagsContainer = document.getElementById('ticker-tags-container');
    if (!tagsContainer) return false;

    const normalized = ticker.trim().toUpperCase();
    if (!normalized) return false;

    // 重複チェック（data-value で厳密に判定）
    if (tagsContainer.querySelector(`.ticker-tag[data-value="${normalized}"]`)) return false;

    const tag = document.createElement('span');
    tag.className = 'ticker-tag';
    tag.dataset.value = normalized;
    tag.innerHTML = `${escapeHtml(normalized)} <button type="button" class="remove-tag-btn text-xs ml-2">×</button>`;

    // 先頭に挿入（左側に表示される）
    tagsContainer.insertBefore(tag, tagsContainer.firstChild);
    return true;
}

// --- 投稿レンダリング関数 ---
/**
 * 投稿リストをDOMにレンダリングする
 * @param {Array} posts - APIから取得した投稿オブジェクトの配列
 * @param {HTMLElement} container - 投稿リストの親要素
 * @param {object} state - app.js の共有state
 */
function renderPostList(posts, container, state) {
    container.innerHTML = '';
    
    if (!posts || posts.length === 0) {
        container.innerHTML = '<p class="text-gray-400 text-center p-4">該当する投稿はありません。</p>';
        return;
    }

    posts.forEach((post, index) => {
        let formattedDate = 'N/A';
        if (post.posted_at_iso) {
            try {
                const date = new Date(post.posted_at_iso);
                formattedDate = date.getFullYear() + '-' +
                              ('0' + (date.getMonth() + 1)).slice(-2) + '-' +
                              ('0' + date.getDate()).slice(-2) + ' ' +
                              ('0' + date.getHours()).slice(-2) + ':' +
                              ('0' + date.getMinutes()).slice(-2);
            } catch (e) { console.warn('Invalid date format:', post.posted_at_iso); }
        }
        
        const linkIcon = post.link_summary ? '<span class="text-yellow-500">🔗</span>' : '';

        // ティッカータグ部分（API経由で取得した post.ticker_sentiments を利用）
        let tickerTagsHtml = '';
        if (post.ticker_sentiments && post.ticker_sentiments.length > 0) {
            post.ticker_sentiments.forEach(ts => {
                let icon = '➖️';
                if (ts.sentiment === 'Positive') icon = '✅️';
                if (ts.sentiment === 'Negative') icon = '❌';
                // data-ticker 属性を付与（表示は大文字化済みで統一していないAPIが来ても安全）
                tickerTagsHtml += `<button type="button" class="ticker-btn text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 border text-white" data-ticker="${escapeHtml((ts.ticker||'').toUpperCase())}">
                                        <span class="font-semibold mr-1">${escapeHtml((ts.ticker||'').toUpperCase())}</span><span class="text-sm">${icon}</span>
                                   </button>`;
            });
        } else {
            tickerTagsHtml = `<span class="text-xs text-gray-500 italic">(銘柄解析なし)</span>`;
        }

        // postHtml の適切箇所に tickerTagsHtml を埋め込む（例: post本文の直後あたり）
        const postHtml = `
        <div id="post-${post.id}" 
             class="post-item rounded shadow p-2 border hover:bg-gray-700 transition duration-150 ease-in-out cursor-pointer"
             data-post-id="${post.id}"
             data-index="${index}">
            <div class="flex justify-between items-start">
                <div class="flex items-center space-x-3">
                    <span class="font-bold text-sm post-username">${escapeHtml(post.username)}</span>
                    <span class="text-xs text-gray-400">${formattedDate}</span>
                </div>
                <div class="flex space-x-3 text-xs text-gray-400 text-right flex-shrink-0">
                    <span>❤️ ${post.like_count ?? 0}</span>
                    <span>🔁 ${post.retweet_count ?? 0}</span>
                    ${linkIcon}
                </div>
            </div>

            <div class="mt-1">
                <div class="post-text text-sm leading-snug"
                     data-original-text="${escapeHtml(post.original_text || '')}">
                </div>
            </div>

            <!-- ここにティッカータグを挿入 -->
            <div class="mt-2 flex flex-wrap gap-2 items-center">
                ${tickerTagsHtml}
            </div>

            <div class="mt-1 text-right">
                <a href="${post.source_url || '#'}" target="_blank" class="text-xs hover:underline">元の投稿 &rarr;</a>
            </div>
        </div>
        `;

        container.insertAdjacentHTML('beforeend', postHtml);
    });

    // HTML挿入後に、テキスト処理 (Autolinker, もっと見る) を実行
    processPostTextDOM(state.autolinker);
    
    // 絞り込み実行時に選択は解除する
    clearSelection(state, elements);
}

// --- 投稿本文の Autolinker と「もっと見る」を適用 ---
function processPostTextDOM(autolinker) {
    const maxLines = 3; 
    const lineHeight = 1.5 * 14;
    const maxHeight = lineHeight * maxLines;

    document.querySelectorAll('.post-text').forEach(el => {
        const rawText = el.dataset.originalText;
        if (!rawText || rawText.trim() === '' || rawText.toLowerCase() === 'none' || rawText.toLowerCase() === 'null') {
            el.innerHTML = '<span class="text-gray-500 italic">[本文なし]</span>';
            return;
        }
        
        let originalText = rawText;
        try {
            const TmpElement = document.createElement('textarea');
            TmpElement.innerHTML = originalText;
            originalText = TmpElement.value;

            const linkedHtml = autolinker.link(originalText);
            el.innerHTML = linkedHtml;

            if (el.scrollHeight > maxHeight && el.scrollHeight > 0) {
                el.classList.add('truncated');
                const toggleBtn = document.createElement('span');
                toggleBtn.textContent = '...もっと見る';
                toggleBtn.className = 'toggle-truncate-btn';
                
                toggleBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (el.classList.contains('truncated')) {
                        el.classList.remove('truncated');
                        toggleBtn.textContent = '閉じる';
                    } else {
                        el.classList.add('truncated');
                        toggleBtn.textContent = '...もっと見る';
                    }
                });
                el.parentNode.appendChild(toggleBtn);
            }
        } catch (innerError) {
            console.error("Error processing post text:", innerError);
            el.innerHTML = '<span class="text-red-500">[本文の表示に失敗しました]</span>';
        }
    });
}

// --- 選択 UI 更新 / クリア ---
function updateSelectionUI(state, elements) {
    const count = state.selectedPostIds.size;
    elements.post.selectionCounter.textContent = `${count}件 選択中`;
    if (elements.action && elements.action.batchBtnCounter) {
        elements.action.batchBtnCounter.textContent = `${count}`;
    }
    
    document.querySelectorAll('.post-item').forEach(item => {
        item.classList.toggle('selected', state.selectedPostIds.has(item.dataset.postId));
    });
}

function clearSelection(state, elements) {
    state.selectedPostIds.clear();
    state.lastClickedIndex = -1;
    updateSelectionUI(state, elements);
}

// --- メイン初期化関数（app.js から呼ばれる） ---
let elements;
let state;

/**
 * ポストペインの全機能（選択、絞り込み、分析）を初期化
 * @param {object} el - app.js から渡されるDOM要素のキャッシュ
 * @param {object} st - app.js から渡される共有state
 */
export function initPostHandler(el, st) {
    elements = el;
    state = st;

    // --- 1. 投稿の選択機能（イベントデリゲーション） ---
    elements.post.listContainer?.addEventListener('click', (e) => {
        const clickedItem = e.target.closest('.post-item');

        // ここでクリック元がリンク・もっと見るボタン・ティッカーボタンなら選択動作を行わない
        if (!clickedItem || e.target.closest('a') || e.target.closest('.toggle-truncate-btn') || e.target.closest('.ticker-btn')) {
            return;
        }

        const clickedPostId = clickedItem.dataset.postId;
        const clickedIndex = parseInt(clickedItem.dataset.index, 10);

        if (e.shiftKey && state.lastClickedIndex !== -1) {
            // Shift選択
            const postItems = Array.from(document.querySelectorAll('.post-item'));
            const start = Math.min(state.lastClickedIndex, clickedIndex);
            const end = Math.max(state.lastClickedIndex, clickedIndex);
            for (let i = start; i <= end; i++) {
                postItems[i] && state.selectedPostIds.add(postItems[i].dataset.postId);
            }
        } else {
            // 通常選択 (トグル)
            state.selectedPostIds.has(clickedPostId) ? state.selectedPostIds.delete(clickedPostId) : state.selectedPostIds.add(clickedPostId);
        }
        
        state.lastClickedIndex = clickedIndex;
        updateSelectionUI(state, elements);
    });

    // 全選択解除ボタン
    elements.post.deselectAllBtn?.addEventListener('click', () => clearSelection(state, elements));

    // --- 2. 絞り込み機能 (API連携) ---
    elements.filter.runBtn?.addEventListener('click', async () => {
        // 1. 検索条件を取得
        const keyword = elements.filter.keywordInput.value.trim();
        const likes = elements.filter.likesInput.value ? parseInt(elements.filter.likesInput.value, 10) : null;
        const rts = elements.filter.rtsInput.value ? parseInt(elements.filter.rtsInput.value, 10) : null;
        
        // タグ群から ticker を取得
        const tickerTags = document.querySelectorAll('#ticker-tags-container .ticker-tag');
        const ticker_list = Array.from(tickerTags).map(tag => tag.dataset.value);

        // 追加: 入力欄の現在値を一時的に検索対象に含める（Enter前のtyping時に対応）
        const tickerInputValue = (document.getElementById('filter-ticker-input') || {}).value;
        if (tickerInputValue && tickerInputValue.trim()) {
            if (!ticker_list.includes(tickerInputValue.trim().toUpperCase())) {
                ticker_list.push(tickerInputValue.trim().toUpperCase());
            }
        }

        const sentiment = elements.filter.sentimentSelect.value;
        const selectedSectors = Array.from(document.querySelectorAll('.sector-parent-cb:checked')).map(cb => cb.value);
        const selectedSubSectors = Array.from(document.querySelectorAll('.sector-child-cb:checked')).map(cb => cb.value);
        const selectedAccountCheckboxes = document.querySelectorAll('.account-filter-checkbox:checked');
        const accounts = Array.from(selectedAccountCheckboxes).map(cb => cb.value);

        // 2. ラベル更新とドロップダウン非表示
        if (accounts.length === 0) {
            elements.accountFilter.label.textContent = 'すべてのアカウント';
        } else {
            elements.accountFilter.label.textContent = `${accounts.length}件のアカウント選択中`;
        }
        elements.accountFilter.menu.classList.add('hidden');
        elements.sectorFilter.menu.classList.add('hidden'); // セクターも閉じる

        // 3. APIにリクエスト
        const btn = elements.filter.runBtn;
        btn.disabled = true;
        btn.textContent = '検索中...';
        elements.post.listContainer.innerHTML = '<p class="text-gray-400 text-center p-4">データを検索しています...</p>';

        try {
            const response = await fetch('/api/filter-posts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword, accounts, likes, rts,
                    ticker: ticker_list,
                    sector: selectedSectors,
                    sub_sector: selectedSubSectors,
                    sentiment
                })
            });

            if (!response.ok) throw new Error(`APIエラー: ${response.statusText}`);
            const result = await response.json();
            if (result.status === 'success') {
                renderPostList(result.posts, elements.post.listContainer, state);
            } else {
                throw new Error(result.message || '不明なサーバーエラー');
            }

        } catch (error) {
            console.error('絞り込みエラー:', error);
            elements.post.listContainer.innerHTML = `<p class="text-red-400 text-center p-4">エラー: ${error.message}</p>`;
        } finally {
            btn.disabled = false;
            btn.textContent = '絞り込み';
        }
    });

    // --- 3. 一括分析実行 (API連携) ---
    const batchBtn = elements.action.batchBtn;
    const resultDisplay = elements.action.resultDisplay;
    const modelSelect = elements.action.modelSelect;
    
    if (batchBtn && modelSelect) {
        batchBtn.addEventListener('click', async () => {
            const postIds = Array.from(state.selectedPostIds).map(id => parseInt(id, 10));
            const promptText = elements.prompt.editor.value;
            const selectedModelName = modelSelect.value;
            const selectedPromptName = elements.prompt.select.options[elements.prompt.select.selectedIndex].text;

            if (postIds.length === 0) { alert('分析する投稿を1件以上選択してください。'); return; }
            if (!promptText) { alert('プロンプトを入力してください。'); return; }
            
            batchBtn.disabled = true;
            batchBtn.innerHTML = '⏱️ 分析中...';
            resultDisplay.innerHTML = `<p class="text-yellow-400">分析を開始します (${selectedModelName} 使用)... AI応答を待機中...</p>`;
            
            try {
                const response = await fetch('/api/analyze-batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        postIds,
                        promptText,
                        modelName: selectedModelName,
                        promptName: selectedPromptName
                    })
                });

                const result = await response.json();
                
                if (response.ok && result.status === 'success') {
                    if (elements.creditMonitor && result.new_balance_usd !== undefined) {
                        elements.creditMonitor.textContent = '$' + result.new_balance_usd.toFixed(6);
                    }
                    
                    const displaySummary = result.summary || "(サマリーなし)";
                    const rawJsonMessage = result.raw_json || "(DBステータスなし)";
                    const usageData = result.usage;
                    const costInfo = result.cost_usd ? 
                        `<span class="text-yellow-500 font-bold">$${result.cost_usd.toFixed(6)} USD</span> (Model: ${result.model})` 
                        : 'コスト情報なし';
                    const tokenInfo = usageData ? 
                        `<span class="text-xs text-gray-400">トークン: Input ${usageData.prompt_tokens} / Output ${usageData.completion_tokens}</span>` 
                        : 'トークン情報なし';

                    let resultHtml = `<p class="text-green-400 font-bold">✅ 一括分析成功 (${result.analyzed_count}件)</p>
                                      <p class="mt-2 text-sm">コスト: ${costInfo}</p>
                                      <p class="mt-1 text-sm">${tokenInfo}</p>
                                      <p class="mt-3 font-semibold text-gray-300">概要 (Summary):</p>
                                      <p class="text-sm italic">${escapeHtml(displaySummary)}</p>
                                      <p class="mt-3 font-semibold text-gray-300">DB格納ステータス:</p>
                                      <pre class="text-xs bg-gray-800 p-2 rounded mt-1 overflow-x-auto">${escapeHtml(rawJsonMessage)}</pre>
                                      <p class="text-xs text-gray-500 mt-2">（結果ID: ${result.result_id} がDBに保存されました）</p>`;
                    
                    resultDisplay.innerHTML = resultHtml;
                    
                } else { 
                    throw new Error(result.message || '不明なエラー');
                }

            } catch (error) {
                console.error('一括分析エラー:', error);
                resultDisplay.innerHTML = `<p class="text-red-400 font-bold">❌ 分析エラー</p><pre class="text-sm mt-1">${error.message}</pre>`;
            } finally {
                batchBtn.disabled = false;
                const count = state.selectedPostIds.size;
                batchBtn.innerHTML = `<span id="batch-btn-counter">${count}</span> 件をまとめて分析実行`;
                const newBatchBtnCounter = document.getElementById('batch-btn-counter'); 
                if(newBatchBtnCounter) newBatchBtnCounter.textContent = count;
            }
        }); 
    }

    // --- 4. 初期読み込み時のテキスト処理 ---
    processPostTextDOM(state.autolinker);

    // --- 5. デリゲーションと自動絞り込みの登録（1回だけ） ---
    // (A) ポストリスト内での ticker-btn クリック（デリゲーション）
    elements.post.listContainer?.addEventListener('click', (e) => {
        const btn = e.target.closest('.ticker-btn');
        if (!btn) return;

        e.stopPropagation();
        e.preventDefault();

        const ticker = (btn.dataset.ticker || '').trim();
        if (!ticker) return;

        const added = addTickerTag(ticker);
        const tickerInput = document.getElementById('filter-ticker-input');
        if (tickerInput) tickerInput.blur();

        if (added) triggerFilterDebounced();
        else triggerFilterDebounced();
    });

    // (B) タグ領域の × 削除をデリゲート
    document.getElementById('ticker-tags-container')?.addEventListener('click', (e) => {
        const rem = e.target.closest('.remove-tag-btn');
        if (!rem) return;
        e.stopPropagation();
        e.preventDefault();
        const tag = rem.closest('.ticker-tag');
        if (tag) tag.remove();
        triggerFilterDebounced();
    });

    // (C) ティッカー検索入力の input イベントで自動絞り込み（入力中も発火）
    // --- 修正箇所: filter 実行時に入力中の値を無条件で ticker_list に追加しない ---
    // 変更前（削除するブロック）:
    // const tickerInputValue = (document.getElementById('filter-ticker-input') || {}).value;
    // if (tickerInputValue && tickerInputValue.trim()) {
    //     if (!ticker_list.includes(tickerInputValue.trim().toUpperCase())) {
    //         ticker_list.push(tickerInputValue.trim().toUpperCase());
    //     }
    // }

    // 代わりに何もしない（タグは addTag / サジェストクリック / Enter で追加される想定）
    // --- さらに修正: initPostHandler 内の tickerInput の 'input' リスナを削除してください ---
    // つまり、以下をファイルから削除する:
    // tickerInputEl.addEventListener('input', () => {
    //     triggerFilterDebounced();
    // });

    // (D) 各種フィルタ入力で自動絞り込み
    elements.filter.keywordInput?.addEventListener('input', triggerFilterDebounced);
    elements.filter.likesInput?.addEventListener('input', triggerFilterDebounced);
    elements.filter.rtsInput?.addEventListener('input', triggerFilterDebounced);
    elements.filter.sentimentSelect?.addEventListener('change', triggerFilterDebounced);

    document.querySelectorAll('.account-filter-checkbox').forEach(cb => cb.addEventListener('change', triggerFilterDebounced));
    document.querySelectorAll('.sector-parent-cb, .sector-child-cb').forEach(cb => cb.addEventListener('change', triggerFilterDebounced));

    elements.filter.resetBtn?.addEventListener('click', () => {
        setTimeout(() => triggerFilterDebounced(), 50);
    });

    // (E) 他モジュールから使えるようにグローバルに公開（サジェスト側などが呼べる）
    //      直接 window に置くのは簡便で、既存コードの修正を最小にします。
    window.addTickerTag = addTickerTag;
    window.triggerFilterDebounced = triggerFilterDebounced;

    // --- 6. 無限スクロールの初期化 ---
    /* 定数 */
    const PAGE_LIMIT = 50;
    const MAX_DOM_POSTS = 200;

    /* nextCursor とロードフラグ（モジュールスコープ） */
    let nextCursor = null;
    let isLoadingMore = false;

    /* DOM トリミング: MAX_DOM_POSTS を超えたら古い要素を削除 */
    function trimOldPosts() {
        const container = elements.post.listContainer;
        if (!container) return;
        while (container.children.length > MAX_DOM_POSTS) {
            container.removeChild(container.firstElementChild);
        }
    }

    /* appendPostList: サーバからの posts を既存DOMに追加する（renderPostList は置換用のまま） */
    function appendPostList(posts) {
        const container = elements.post.listContainer;
        if (!container || !posts || posts.length === 0) return;

        const fragment = document.createDocumentFragment();

        posts.forEach((post) => {
            // 既存の renderPostList と同じ HTML 構成をここでも使う（軽量化のため同様のテンプレを利用）
            const formattedDate = post.posted_at_iso ? (new Date(post.posted_at_iso)).toISOString().slice(0,16).replace('T',' ') : 'N/A';
            const linkIcon = post.link_summary ? '<span class="text-yellow-500">🔗</span>' : '';

            let tickerTagsHtml = '';
            if (post.ticker_sentiments && post.ticker_sentiments.length > 0) {
                post.ticker_sentiments.forEach(ts => {
                    let icon = '➖️';
                    if (ts.sentiment === 'Positive') icon = '✅️';
                    if (ts.sentiment === 'Negative') icon = '❌';
                    tickerTagsHtml += `<button type="button" class="ticker-btn text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 border text-white" data-ticker="${escapeHtml((ts.ticker||'').toUpperCase())}">
                                            <span class="font-semibold mr-1">${escapeHtml((ts.ticker||'').toUpperCase())}</span><span class="text-sm">${icon}</span>
                                    </button>`;
                });
            } else {
                tickerTagsHtml = `<span class="text-xs text-gray-500 italic">(銘柄解析なし)</span>`;
            }

            const postHtml = `
            <div id="post-${post.id}" 
                class="post-item rounded shadow p-2 border hover:bg-gray-700 transition duration-150 ease-in-out cursor-pointer"
                data-post-id="${post.id}"
                data-index="${container.children.length}">
                <div class="flex justify-between items-start">
                    <div class="flex items-center space-x-3">
                        <span class="font-bold text-sm post-username">${escapeHtml(post.username)}</span>
                        <span class="text-xs text-gray-400">${formattedDate}</span>
                    </div>
                    <div class="flex space-x-3 text-xs text-gray-400 text-right flex-shrink-0">
                        <span>❤️ ${post.like_count ?? 0}</span>
                        <span>🔁 ${post.retweet_count ?? 0}</span>
                        ${linkIcon}
                    </div>
                </div>

                <div class="mt-1">
                    <div class="post-text text-sm leading-snug"
                        data-original-text="${escapeHtml(post.original_text || '')}">
                    </div>
                </div>

                <div class="mt-2 flex flex-wrap gap-2 items-center">
                    ${tickerTagsHtml}
                </div>

                <div class="mt-1 text-right">
                    <a href="${post.source_url || '#'}" target="_blank" class="text-xs hover:underline">元の投稿 &rarr;</a>
                </div>
            </div>
            `;
            const temp = document.createElement('div');
            temp.innerHTML = postHtml;
            fragment.appendChild(temp.firstElementChild);
        });

        container.appendChild(fragment);

        // Text processing for newly added posts
        processPostTextDOM(state.autolinker);
        clearSelection(state, elements);
        trimOldPosts();
    }

    /* loadMorePosts: nextCursor が存在する限りサーバへ追加取得 */
    async function loadMorePosts() {
        if (isLoadingMore) return;
        if (!nextCursor) return;
        isLoadingMore = true;

        try {
            // gather current filter params (same as runBtn)
            const keyword = elements.filter.keywordInput.value.trim();
            const likes = elements.filter.likesInput.value ? parseInt(elements.filter.likesInput.value, 10) : null;
            const rts = elements.filter.rtsInput.value ? parseInt(elements.filter.rtsInput.value, 10) : null;
            const tickerTags = document.querySelectorAll('#ticker-tags-container .ticker-tag');
            const ticker_list = Array.from(tickerTags).map(tag => tag.dataset.value);
            const sentiment = elements.filter.sentimentSelect.value;
            const selectedSectors = Array.from(document.querySelectorAll('.sector-parent-cb:checked')).map(cb => cb.value);
            const selectedSubSectors = Array.from(document.querySelectorAll('.sector-child-cb:checked')).map(cb => cb.value);
            const selectedAccountCheckboxes = document.querySelectorAll('.account-filter-checkbox:checked');
            const accounts = Array.from(selectedAccountCheckboxes).map(cb => cb.value);

            // --- runBtn の fetch 部分を以下で置き換え ---
            const response = await fetch('/api/filter-posts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    keyword, accounts, likes, rts,
                    ticker: ticker_list,
                    sector: selectedSectors,
                    sub_sector: selectedSubSectors,
                    sentiment,
                    limit: PAGE_LIMIT,
                    cursor: null // initial search
                })
            });

            if (!response.ok) throw new Error(`APIエラー: ${response.statusText}`);
            const result = await response.json();
            if (result.status === 'success') {
                // initial render replaces content
                renderPostList(result.posts, elements.post.listContainer, state);
                // set nextCursor for subsequent loads
                nextCursor = result.next_cursor;
            } else {
                throw new Error(result.message || '不明なサーバーエラー');
            }
        } catch (e) {
            console.error('loadMorePosts failed:', e);
        } finally {
            isLoadingMore = false;
        }
    }

    /* --- 修正: runBtn click ハンドラの body で limit と cursor を渡し、nextCursor をセットする ---
    locate the runBtn handler in initPostHandler and replace the API call section with the block below.
    */

    // --- initPostHandler の末尾に追加 ---
    (function setupInfiniteScrollSentinel() {
        const sentinel = document.createElement('div');
        sentinel.id = 'infinite-scroll-sentinel';
        // append sentinel after the post list container (so it will appear at the end)
        elements.post.listContainer.parentElement.appendChild(sentinel);

        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    // only attempt to load more if nextCursor is set
                    if (nextCursor) loadMorePosts();
                }
            });
        }, { root: null, rootMargin: '400px', threshold: 0.1 });

        observer.observe(sentinel);
    })();
    
}