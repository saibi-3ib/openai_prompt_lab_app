// --- 内部ヘルパー関数 ---

/**
 * 投稿リストをDOMにレンダリングする
 * @param {Array} posts - APIから取得した投稿オブジェクトの配列
 * @param {HTMLElement} container - 投稿リストの親要素
 * @param {object} state - app.js の共有state
 */
function renderPostList(posts, container, state) {
    container.innerHTML = '';
    
    if (posts.length === 0) {
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
                tickerTagsHtml += `<button type="button" class="ticker-btn text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 border text-white" data-ticker="${escapeHtml(ts.ticker)}">
                                        <span class="font-semibold mr-1">${escapeHtml(ts.ticker)}</span><span class="text-sm">${icon}</span>
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
                    <span class="font-bold text-sm post-username">${post.username}</span>
                    <span class="text-xs text-gray-400">${formattedDate}</span>
                </div>
                <div class="flex space-x-3 text-xs text-gray-400 text-right flex-shrink-0">
                    <span>❤️ ${post.like_count}</span>
                    <span>🔁 ${post.retweet_count}</span>
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
                <a href="${post.source_url}" target="_blank" class="text-xs hover:underline">元の投稿 &rarr;</a>
            </div>
        </div>
        `;

        container.insertAdjacentHTML('beforeend', postHtml);

        // 追加: 生成した .ticker-btn に対するクリック動作をバインド（タグクリックでフィルタをセットして検索トリガ）
        const inserted = container.querySelector(`#post-${post.id}`);
        if (inserted) {
            inserted.querySelectorAll('.ticker-btn').forEach(btn => {
                btn.addEventListener('click', (ev) => {
                    ev.stopPropagation(); // ポスト選択クリックの伝播を止める
                    const ticker = btn.dataset.ticker;
                    // ticker-tags-container に同じタグがなければ追加する
                    const tagsContainer = document.getElementById('ticker-tags-container');
                    if (tagsContainer && !tagsContainer.querySelector(`.ticker-tag[data-value="${ticker}"]`)) {
                        const tag = document.createElement('span');
                        tag.className = 'ticker-tag bg-gray-700 text-xs px-2 py-1 rounded flex items-center gap-2';
                        tag.dataset.value = ticker;
                        tag.innerHTML = `${ticker} <button type="button" class="remove-tag-btn text-xs ml-2">×</button>`;
                        tagsContainer.appendChild(tag);
                    }
                    // 既存の「実行」ボタンをクリックしてフィルタを発動（initPostHandler 内のハンドラを活用）
                    const runBtn = document.getElementById('filter-run-btn');
                    if (runBtn) runBtn.click();
                });
            });
        }
        // --- 追加修正: initPostHandler の post-item クリックハンドラで、ticker-btn クリック時は選択動作を無視する ---
        // （既存の条件に e.target.closest('.ticker-btn') の判定を追加してください）
        // 例: if (!clickedItem || e.target.closest('a') || e.target.closest('.toggle-truncate-btn') || e.target.closest('.ticker-btn')) { return; }
    });

    // HTML挿入後に、テキスト処理 (Autolinker, もっと見る) を実行
    processPostTextDOM(state.autolinker);
    
    // 絞り込み実行時に選択は解除する
    clearSelection(state, elements);
}

/**
 * 投稿本文の Autolinker と「もっと見る」を適用
 * @param {object} autolinker - Autolinker インスタンス
 */
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

/**
 * 選択状態のUI（カウンターなど）を更新
 * @param {object} state - app.js の共有state
 * @param {object} elements - app.js のDOM要素
 */
function updateSelectionUI(state, elements) {
    const count = state.selectedPostIds.size;
    elements.post.selectionCounter.textContent = `${count}件 選択中`;
    elements.action.batchBtnCounter.textContent = `${count}`;
    
    document.querySelectorAll('.post-item').forEach(item => {
        item.classList.toggle('selected', state.selectedPostIds.has(item.dataset.postId));
    });
}

/**
 * すべての選択を解除
 * @param {object} state - app.js の共有state
 * @param {object} elements - app.js のDOM要素
 */
function clearSelection(state, elements) {
    state.selectedPostIds.clear();
    state.lastClickedIndex = -1;
    updateSelectionUI(state, elements);
}

/**
 * HTMLエスケープ用ヘルパー
 */
function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/"/g, '&quot;')
              .replace(/'/g, '&#39;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/\n/g, '&#10;');
}


// --- メインの初期化関数 (app.js から呼ばれる) ---

// (★) グローバルスコープで elements を保持 (コールバック関数で使うため)
let elements;
let state;

/**
 * ポストペインの全機能（選択、絞り込み、分析）を初期化
 * @param {object} el - app.js から渡されるDOM要素のキャッシュ
 * @param {object} st - app.js から渡される共有state
 */
export function initPostHandler(el, st) {
    // (★) elements と state をモジュール変数にキャッシュ
    elements = el;
    state = st;

    // --- 1. 投稿の選択機能 ---
    elements.post.listContainer?.addEventListener('click', (e) => {
        const clickedItem = e.target.closest('.post-item');
        
        if (!clickedItem || e.target.closest('a') || e.target.closest('.toggle-truncate-btn')) {
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
        
        const tickerTags = document.querySelectorAll('#ticker-tags-container .ticker-tag');
        const ticker_list = Array.from(tickerTags).map(tag => tag.dataset.value);
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
        elements.sectorFilter.menu.classList.add('hidden'); // (★) セクターも閉じる

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
                // (★) batchBtnCounter はHTMLが再生成されるので、elements から再取得して更新する
                const newBatchBtnCounter = document.getElementById('batch-btn-counter'); 
                if(newBatchBtnCounter) newBatchBtnCounter.textContent = count;
            }
        }); 
    }

    // --- 4. 初期読み込み時のテキスト処理 ---
    // (サーバーサイドレンダリングされた投稿に対して実行)
    processPostTextDOM(state.autolinker);
}