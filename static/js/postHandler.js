// --- postHandler.js (corrected) ---
// Responsibilities:
// - renderPostList / appendPostList
// - initPostHandler: wire up event handlers (selection, filtering, batch analysis)
// - Delegated handling for .ticker-btn and ticker-tag removal
// - Infinite scroll (keyset pagination) using /api/filter-posts (limit + cursor)
// NOTE: Keep helper functions (escapeHtml, processPostTextDOM) here.

/////////////////////
// Module-scope constants / state
/////////////////////
const PAGE_LIMIT = 50;
const MAX_DOM_POSTS = 200;

let elements; // assigned in initPostHandler
let state;    // assigned in initPostHandler
let nextCursor = null;
let isLoadingMore = false;

/////////////////////
// Helpers
/////////////////////
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
function triggerFilter() {
    const runBtn = elements?.filter?.runBtn || document.getElementById('filter-run-btn');
    if (runBtn) runBtn.click();
}
const triggerFilterDebounced = debounce(() => triggerFilter(), 250);

// expose debounced filter trigger so other modules (uiControls etc.) can call it
window.triggerFilterDebounced = triggerFilterDebounced;

// 更新用関数: 選択数を表示に反映し、.post-item に selected クラスを付け外しする
function updateSelectionUI(st = state, el = elements) {
    const count = (st && st.selectedPostIds) ? st.selectedPostIds.size : 0;
    try {
        if (el && el.post && el.post.selectionCounter) {
            el.post.selectionCounter.textContent = `${count}件 選択中`;
        }
        if (el && el.action && el.action.batchBtnCounter) {
            el.action.batchBtnCounter.textContent = `${count}`;
        }
    } catch (e) {
        // ignore UI update errors in edge cases
        console.warn('updateSelectionUI: UI elements missing', e);
    }

    // post-item に selected クラスを付与/削除（DOM 全体をスキャン）
    document.querySelectorAll('.post-item').forEach(item => {
        const pid = item.dataset.postId;
        const selected = !!(st && st.selectedPostIds && st.selectedPostIds.has(pid));
        item.classList.toggle('selected', selected);
    });
}

// クリア関数: 選択セットを空にして UI を更新する
function clearSelection(st = state, el = elements) {
    if (!st) return;
    // 保守的に selectedPostIds が未定義なら初期化
    if (!st.selectedPostIds || !(st.selectedPostIds instanceof Set)) {
        st.selectedPostIds = new Set();
    } else {
        st.selectedPostIds.clear();
    }
    st.lastClickedIndex = -1;
    updateSelectionUI(st, el);
}

/////////////////////
// Ticker tag helpers (single definition)
/////////////////////
function addTickerTag(ticker) {
    if (!ticker) return false;
    const tagsContainer = document.getElementById('ticker-tags-container');
    if (!tagsContainer) return false;
    const normalized = ticker.trim().toUpperCase();
    if (!normalized) return false;
    if (tagsContainer.querySelector(`.ticker-tag[data-value="${normalized}"]`)) return false;
    const tag = document.createElement('span');
    tag.className = 'ticker-tag';
    tag.dataset.value = normalized;
    tag.innerHTML = `${escapeHtml(normalized)} <button type="button" class="remove-tag-btn text-xs ml-2">×</button>`;
    tagsContainer.insertBefore(tag, tagsContainer.firstChild);
    return true;
}
window.addTickerTag = addTickerTag; // allow other modules to call

/////////////////////
// Rendering: render (replace) and append
/////////////////////
function renderPostList(posts, container, st) {
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
        let tickerTagsHtml = '';
        if (post.ticker_sentiments && post.ticker_sentiments.length > 0) {
            post.ticker_sentiments.forEach(ts => {
                let icon = '➖️';
                if (ts.sentiment === 'Positive') icon = '✅';
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
    processPostTextDOM(st.autolinker);
    clearSelection(state, elements);
}

function appendPostList(posts) {
    const container = elements.post.listContainer;
    if (!container || !posts || posts.length === 0) return;
    const fragment = document.createDocumentFragment();
    posts.forEach((post) => {
        const formattedDate = post.posted_at_iso ? (new Date(post.posted_at_iso)).toISOString().slice(0,16).replace('T',' ') : 'N/A';
        const linkIcon = post.link_summary ? '<span class="text-yellow-500">🔗</span>' : '';
        let tickerTagsHtml = '';
        if (post.ticker_sentiments && post.ticker_sentiments.length > 0) {
            post.ticker_sentiments.forEach(ts => {
                let icon = '➖️';
                if (ts.sentiment === 'Positive') icon = '✅';
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
    processPostTextDOM(state.autolinker);
    clearSelection(state, elements);
    trimOldPosts();
}

/////////////////////
// DOM trimming & load more
/////////////////////
function trimOldPosts() {
    const container = elements.post.listContainer;
    if (!container) return;
    while (container.children.length > MAX_DOM_POSTS) {
        container.removeChild(container.firstElementChild);
    }
}

async function loadMorePosts() {
    if (isLoadingMore) return;
    if (!nextCursor) return;
    isLoadingMore = true;
    try {
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
                cursor: nextCursor
            })
        });

        if (!response.ok) throw new Error(`API error: ${response.statusText}`);
        const result = await response.json();
        if (result.status === 'success') {
            appendPostList(result.posts);
            nextCursor = result.next_cursor ?? null;
            console.log('loadMorePosts: new nextCursor =', nextCursor);
        } else {
            console.warn('loadMorePosts: result.status !== success', result);
        }
    } catch (e) {
        console.error('loadMorePosts failed:', e);
    } finally {
        isLoadingMore = false;
    }
}

/////////////////////
// Post text processing (autolinker, truncate)
/////////////////////
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

/////////////////////
// Main initializer (exported)
/////////////////////
export function initPostHandler(el, st) {
    elements = el;
    state = st;

    // selection handling
    // 1) 投稿クリック（選択、Shift選択） — data-index に依存しない安定版
    elements.post.listContainer?.addEventListener('click', (e) => {
        const clickedItem = e.target.closest('.post-item');
        if (!clickedItem) return;

        // クリック元がリンク・もっと見るボタン・ティッカーボタンなら選択動作を行わない
        if (e.target.closest('a') || e.target.closest('.toggle-truncate-btn') || e.target.closest('.ticker-btn')) {
            return;
        }

        // 動的に index を取得（dataset.index に依存しない）
        const postItems = Array.from(document.querySelectorAll('.post-item'));
        const clickedIndex = postItems.indexOf(clickedItem);
        if (clickedIndex === -1) {
            // 保険: dataset.index を fallback に使う
            const di = parseInt(clickedItem.dataset.index || '-1', 10);
            if (di >= 0) state.lastClickedIndex = di;
            return;
        }

        const clickedPostId = clickedItem.dataset.postId;

        if (e.shiftKey && state.lastClickedIndex !== -1) {
            const start = Math.min(state.lastClickedIndex, clickedIndex);
            const end = Math.max(state.lastClickedIndex, clickedIndex);
            for (let i = start; i <= end; i++) {
                if (postItems[i]) state.selectedPostIds.add(postItems[i].dataset.postId);
            }
        } else {
            // 通常選択 (トグル)
            if (state.selectedPostIds.has(clickedPostId)) state.selectedPostIds.delete(clickedPostId);
            else state.selectedPostIds.add(clickedPostId);
        }

        state.lastClickedIndex = clickedIndex;
        updateSelectionUI(state, elements);
    });

    // 2) ティッカー系のデリゲーション（もし未登録なら） — 投稿内のボタンからタグ追加し絞り込み
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

        if (window.triggerFilterDebounced) window.triggerFilterDebounced();
    });

    // 3) タグ削除デリゲーション（もし未登録なら）
    document.getElementById('ticker-tags-container')?.addEventListener('click', (e) => {
        const rem = e.target.closest('.remove-tag-btn');
        if (!rem) return;
        e.stopPropagation();
        e.preventDefault();
        const tag = rem.closest('.ticker-tag');
        if (tag) tag.remove();
        if (window.triggerFilterDebounced) window.triggerFilterDebounced();
    });

    // 4) Enterキーで絞り込みを発火（keyword, likes, rts 等）
    ['keywordInput','likesInput','rtsInput'].forEach(idKey => {
        const el = elements.filter && elements.filter[idKey];
        if (!el) return;
        el.addEventListener('keydown', (ev) => {
            if (ev.key === 'Enter') {
                ev.preventDefault();
                // 即時発火（debounced でも OK。即時が好みなら直接 triggerFilter();）
                if (window.triggerFilterDebounced) window.triggerFilterDebounced();
                else triggerFilter(); // fallback
            }
        });
    });

    // 5) select やチェックボックスの click/change で即座に debounced 発火（念のため再登録）
    elements.filter.sentimentSelect?.addEventListener('change', triggerFilterDebounced);
    document.querySelectorAll('.account-filter-checkbox').forEach(cb => {
        // ensure not double-registered if already attached - you can check console log for duplicates
        cb.removeEventListener?.('change', triggerFilterDebounced); // safe no-op if not present
        cb.addEventListener('change', triggerFilterDebounced);
    });
    document.querySelectorAll('.sector-parent-cb, .sector-child-cb').forEach(cb => {
        cb.removeEventListener?.('change', triggerFilterDebounced);
        cb.addEventListener('change', triggerFilterDebounced);
    });

    elements.post.deselectAllBtn?.addEventListener('click', () => clearSelection(state, elements));

    // run / filter button handler (initial search)
    elements.filter.runBtn?.addEventListener('click', async () => {
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

        if (accounts.length === 0) {
            elements.accountFilter.label.textContent = 'すべてのアカウント';
        } else {
            elements.accountFilter.label.textContent = `${accounts.length}件のアカウント選択中`;
        }
        elements.accountFilter.menu.classList.add('hidden');
        elements.sectorFilter.menu.classList.add('hidden');

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
                    sentiment,
                    limit: PAGE_LIMIT,
                    cursor: null
                })
            });

            if (!response.ok) throw new Error(`APIエラー: ${response.statusText}`);
            const result = await response.json();
            if (result.status === 'success') {
                renderPostList(result.posts, elements.post.listContainer, state);
                nextCursor = result.next_cursor ?? null;
                console.log('filter run: next_cursor =', nextCursor);
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

    // batch analysis handlers kept unchanged...
    // (omitted here for brevity - keep original handlers already present)

    // other UI handlers (filters, tag removal) should be registered here as originally implemented
    // (we assume those lines remain in this function; if missing, re-add them)

    // Ensure initial server-rendered posts get processed and displayed
    try {
        processPostTextDOM(state.autolinker);
    } catch (e) {
        console.warn('processPostTextDOM initial run failed:', e);
    }

    // Setup IntersectionObserver sentinel inside the post list container
    (function setupAdaptiveInfiniteScroll() {
    const container = elements?.post?.listContainer;
    if (!container) {
        console.warn('InfiniteScroll: post list container not found.');
        return;
    }

    // Remove previous sentinel if exists to avoid duplicates
    let existing = document.getElementById('infinite-scroll-sentinel');
    if (existing) existing.remove();

    // Decide whether container itself is the scroll viewport
    const isContainerScrollable = container.scrollHeight > container.clientHeight && /auto|scroll/.test(getComputedStyle(container).overflowY);

    // Create sentinel element and append it appropriately
    const sentinel = document.createElement('div');
    sentinel.id = 'infinite-scroll-sentinel';
    sentinel.style.height = '1px';
    sentinel.style.width = '100%';

    if (isContainerScrollable) {
        // append inside container so intersection is relative to container's viewport
        container.appendChild(sentinel);
    } else {
        // container is not the scrolling element: append sentinel after container so root=null (viewport) can observe it
        container.parentElement && container.parentElement.appendChild(sentinel);
    }

    const observerOptions = {
        root: isContainerScrollable ? container : null, // container or viewport
        rootMargin: '200px 0px',
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                console.log('InfiniteScroll: sentinel intersecting, nextCursor=', nextCursor, 'rootIsContainer=', isContainerScrollable);
                if (nextCursor) {
                    loadMorePosts();
                } else {
                    console.log('InfiniteScroll: nextCursor is null, no more pages to load or initial search did not set nextCursor.');
                }
            }
        });
    }, observerOptions);

    observer.observe(sentinel);

    // debug helpers
    window.__loadMorePostsForDebug = loadMorePosts;
    Object.defineProperty(window, 'nextCursorDebug', { get: () => nextCursor });

    console.log('InfiniteScroll: adaptive sentinel attached. containerScrollable=', isContainerScrollable);
})();
}