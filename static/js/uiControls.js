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

    // 新しいタグをDOMに追加する関数
    function addTag(value) {
        const tickerValue = value.toUpperCase();
        if (selectedTickers.has(tickerValue) || !tickerValue) {
            inputEl.value = '';
            return;
        }
        
        selectedTickers.add(tickerValue);

        const tagDiv = document.createElement('div');
        tagDiv.className = 'ticker-tag';
        tagDiv.dataset.value = tickerValue;
        tagDiv.textContent = tickerValue;
        
        const removeBtn = document.createElement('span');
        removeBtn.className = 'ticker-tag-remove';
        removeBtn.textContent = 'x';
        
        removeBtn.addEventListener('click', () => {
            selectedTickers.delete(tickerValue);
            tagDiv.remove();
        });
        
        tagDiv.appendChild(removeBtn);
        inputEl.parentElement.before(tagDiv);
        
        inputEl.value = '';
        suggestionsEl.innerHTML = '';
        suggestionsEl.classList.add('hidden');
        inputEl.focus();
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
                        
                        div.addEventListener('click', () => {
                            addTag(item.value); // item.value = "AAPL"
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