// --- 内部ヘルパー関数 (モジュール内でのみ使用) ---

/**
 * フィルターボタンのラベル（選択件数）を更新する
 */
function updateFilterLabels(elements) {
    // アカウント
    const selectedAccounts = document.querySelectorAll('.account-filter-checkbox:checked').length;
    elements.accountFilter.label.textContent = selectedAccounts === 0 ? 'すべてのアカウント' : `${selectedAccounts}件のアカウント選択中`;
    
    // セクター
    const selectedSectors = document.querySelectorAll('.sector-parent-cb:checked, .sector-child-cb:checked').length;
    if (elements.sectorFilter.label) {
        elements.sectorFilter.label.textContent = selectedSectors === 0 ? 'すべて' : `${selectedSectors}件のセクター選択中`;
    }
}

/**
 * オートサジェスト機能（ティッカー用）
 */
function setupAutocomplete(elements) {
    const inputEl = elements.tickerFilter.input;
    const suggestionsEl = elements.tickerFilter.suggestions;
    const tagsContainer = elements.tickerFilter.tagsContainer;
    
    const selectedTickers = new Set();
    let debounceTimer;

    // 新しいタグをDOMに追加する関数（安全にDOMで構築、innerHTML を使わない）
    function addTag(value) {
        if (!value) return;
        const tickerValueRaw = String(value).trim();
        if (!tickerValueRaw) return;

        // 正規化（重複防止のため大文字化）
        const tickerValue = tickerValueRaw.toUpperCase();

        // selectedTickers Set と DOM の両方で重複チェックを行う（堅牢化）
        if (selectedTickers.has(tickerValue)) {
            inputEl.value = '';
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.add('hidden');
            return;
        }
        // Also check DOM container (in case other code added a tag)
        if (tagsContainer.querySelector(`.ticker-tag[data-value="${tickerValue}"]`)) {
            selectedTickers.add(tickerValue); // keep Set in sync
            inputEl.value = '';
            suggestionsEl.innerHTML = '';
            suggestionsEl.classList.add('hidden');
            return;
        }

        selectedTickers.add(tickerValue);

        // 要素を安全に構築（テキストは textContent で挿入）
        const tagDiv = document.createElement('span');
        tagDiv.className = 'ticker-tag';
        tagDiv.dataset.value = tickerValue;

        const textSpan = document.createElement('span');
        textSpan.textContent = tickerValue;
        tagDiv.appendChild(textSpan);

        const remBtn = document.createElement('button');
        remBtn.type = 'button';
        remBtn.className = 'remove-tag-btn text-xs ml-2';
        remBtn.textContent = '×';
        tagDiv.appendChild(remBtn);

        // 先頭に挿入して「左側に表示」されるようにする
        if (tagsContainer.firstChild) tagsContainer.insertBefore(tagDiv, tagsContainer.firstChild);
        else tagsContainer.appendChild(tagDiv);

        // クリアとサジェスト非表示
        inputEl.value = '';
        suggestionsEl.innerHTML = '';
        suggestionsEl.classList.add('hidden');

        // 削除ボタンの動作（ローカルで Set を更新）
        remBtn.addEventListener('click', (ev) => {
            ev.stopPropagation();
            ev.preventDefault();
            selectedTickers.delete(tickerValue);
            tagDiv.remove();
            // 自動絞り込み（debounced）がある場合は呼ぶ
            if (window.triggerFilterDebounced) window.triggerFilterDebounced();
        });

        // 追加後は自動絞り込み（debounced）が公開されていれば呼び出す
        if (window.triggerFilterDebounced) window.triggerFilterDebounced();
    }

    // 入力イベント
    inputEl.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => {
            const query = inputEl.value.trim();
            if (query.length < 1) {
                suggestionsEl.innerHTML = '';
                suggestionsEl.classList.add('hidden');
                return;
            }
            
            try {
                const response = await fetch(`/api/suggest`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: 'ticker', q: query })
                });
                
                const suggestions = await response.json();

                if (suggestions.length > 0) {
                    suggestionsEl.innerHTML = ''; 
                    suggestions.forEach(item => {
                        const div = document.createElement('div');
                        div.className = 'autocomplete-suggestion';
                        div.textContent = item.label; // "AAPL (Apple Inc.)"
                        
                        // クリックで addTag(item.value) を呼ぶ（item.value is ticker only）
                        div.addEventListener('click', () => {
                            // call addTag with ticker (item.value)
                            addTag(item.value);
                        });
                        
                        suggestionsEl.appendChild(div);
                    });
                    suggestionsEl.classList.remove('hidden');
                } else {
                    suggestionsEl.innerHTML = '';
                    suggestionsEl.classList.add('hidden');
                }
            } catch (error) {
                 console.error("Ticker suggestion fetch error:", error);
                 suggestionsEl.innerHTML = '';
                 suggestionsEl.classList.add('hidden');
            }
        }, 300);
    });
    
    // Enterキーでもタグを追加
    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && inputEl.value.trim() !== '') {
            e.preventDefault(); 
            addTag(inputEl.value.trim());
        }
    });

    // タグコンテナ自体をクリックしても入力欄にフォーカス
    tagsContainer.addEventListener('click', (e) => {
        if (e.target === tagsContainer) {
            inputEl.focus();
        }
    });
    
    return selectedTickers;
}

// --- メインの初期化関数 (app.js から呼ばれる) ---

/**
 * フィルターペインとアクションペインのUIコントロールを初期化
 * @param {object} elements - app.js から渡されるDOM要素のキャッシュ
 */
export function initUiControls(elements) {
    
    // --- 1. ペインの折りたたみ機能 ---
    try {
        // 下部アクションペイン
        elements.action.toggleBtn?.addEventListener('click', () => {
            elements.action.wrapper.classList.toggle('collapsed');
        });

        // 上部フィルターペイン
        elements.filter.toggleBtn?.addEventListener('click', () => {
            elements.filter.wrapper.classList.toggle('collapsed');
        });

    } catch (error) { console.error("Fatal error during collapsible pane setup:", error); }

    // --- 2. ドロップダウン共通ロジック (外側クリックで閉じる) ---
    document.addEventListener('click', (e) => {
        // アカウント
        if (elements.accountFilter.btn && !elements.accountFilter.btn.contains(e.target) && !elements.accountFilter.menu.contains(e.target)) {
            elements.accountFilter.menu.classList.add('hidden');
        }
        // セクター
        if (elements.sectorFilter.btn && !elements.sectorFilter.btn.contains(e.target) && !elements.sectorFilter.menu.contains(e.target)) {
            elements.sectorFilter.menu.classList.add('hidden');
        }
        // ティッカー (サジェスト)
        if (elements.tickerFilter.tagsContainer && !elements.tickerFilter.tagsContainer.contains(e.target) && !elements.tickerFilter.suggestions.contains(e.target)) {
            elements.tickerFilter.suggestions.classList.add('hidden');
        }
    });

    // --- 3. アカウントフィルター ---
    elements.accountFilter.btn?.addEventListener('click', (e) => {
        e.stopPropagation();
        elements.accountFilter.menu.classList.toggle('hidden');
    });

    // --- 4. 階層型セクターフィルター ---
    if (elements.sectorFilter.btn && elements.sectorFilter.menu) {
        
        // ドロップダウンの表示/非表示
        elements.sectorFilter.btn.addEventListener('click', (e) => {
            e.stopPropagation();
            elements.sectorFilter.menu.classList.toggle('hidden');
        });

        // 親子の連動
        elements.sectorFilter.menu.addEventListener('change', (e) => {
            const menu = elements.sectorFilter.menu;

            // (親 -> 子)
            if (e.target.classList.contains('sector-parent-cb')) {
                const parentName = e.target.dataset.sectorName;
                const isChecked = e.target.checked;
                const children = menu.querySelectorAll(`.sector-child-cb[data-parent-sector="${parentName}"]`);
                children.forEach(child => child.checked = isChecked);
            }
            
            // (子 -> 親)
            if (e.target.classList.contains('sector-child-cb')) {
                const parentName = e.target.dataset.parentSector;
                const parentCheckbox = menu.querySelector(`.sector-parent-cb[data-sector-name="${parentName}"]`);
                if (parentCheckbox) {
                    const siblings = menu.querySelectorAll(`.sector-child-cb[data-parent-sector="${parentName}"]`);
                    const allChecked = Array.from(siblings).every(child => child.checked);
                    const noneChecked = Array.from(siblings).every(child => !child.checked);
                    
                    if (allChecked) {
                        parentCheckbox.checked = true;
                        parentCheckbox.indeterminate = false;
                    } else if (!noneChecked) {
                        parentCheckbox.checked = false;
                        parentCheckbox.indeterminate = true;
                    } else {
                        parentCheckbox.checked = false;
                        parentCheckbox.indeterminate = false;
                    }
                }
            }
            
            updateFilterLabels(elements);
        });
    }

    // --- 5. ティッカー (オートコンプリート) ---
    if(elements.tickerFilter.input) {
        setupAutocomplete(elements);
    }
    
    // --- 6. 絞り込みリセットボタン ---
    elements.filter.resetBtn?.addEventListener('click', () => {
        location.reload();
    });
}