// --- メインの初期化関数 (app.js から呼ばれる) ---

// (★) グローバルスコープで elements と state を保持 (コールバック関数で使うため)
let elements;
let state;

/**
 * プロンプト管理機能（ロード、保存、削除）を初期化
 * @param {object} el - app.js から渡されるDOM要素のキャッシュ
 * @param {object} st - app.js から渡される共有state
 */
export function initPromptHandler(el, st) {
    // (★) elements と state をモジュール変数にキャッシュ
    elements = el;
    state = st;
    
    // --- 1. イベントリスナーの登録 ---

    // (A) 「上書き保存」ボタン
    elements.prompt.saveBtn?.addEventListener('click', handleSavePrompt);
    
    // (B) 「削除」ボタン
    elements.prompt.deleteBtn?.addEventListener('click', handleDeletePrompt);
    
    // (C) 「名前を付けて新規保存」ボタン
    elements.prompt.saveAsNewBtn?.addEventListener('click', handleSaveAsNewPrompt);
    
    // (D) ドロップダウン変更時にエディタの内容を更新
    elements.prompt.select?.addEventListener('change', handleDropdownChange);
    
    // --- 2. 初期化処理の実行 ---
    
    // (E) 起動時にプロンプト一覧をロード
    loadPromptsIntoDropdown();
}


// --- 内部ヘルパー関数 ---

/**
 * (A) DBからプロンプト一覧をロードし、ドロップダウンを生成
 */
async function loadPromptsIntoDropdown() {
    try {
        const response = await fetch('/api/get-prompts');
        if (!response.ok) throw new Error('APIからプロンプトを取得できませんでした。');
        
        const prompts = await response.json();
        
        // データをグローバルストアに保存
        state.promptStore = prompts;
        
        elements.prompt.select.innerHTML = ''; // ドロップダウンをクリア
        
        let defaultPromptText = '';

        prompts.forEach(prompt => {
            const option = document.createElement('option');
            option.value = prompt.id;
            option.textContent = prompt.name;
            elements.prompt.select.appendChild(option);
            
            // デフォルトプロンプトのテキストを保持
            if (prompt.is_default || prompts.length === 1) {
                defaultPromptText = prompt.template_text;
                option.selected = true; // デフォルトを選択状態にする
            }
        });
        
        // デフォルトプロンプトをエディタに表示
        elements.prompt.editor.value = defaultPromptText;

    } catch (error) {
        console.error("プロンプトのロードに失敗:", error);
        elements.prompt.editor.value = "エラー: プロンプトのロードに失敗しました。";
    }
}

/**
 * (B) 「上書き保存」ボタンの処理
 */
async function handleSavePrompt() {
    const selectedId = parseInt(elements.prompt.select.value, 10);
    const editorText = elements.prompt.editor.value;

    if (!selectedId) { alert("プロンプトが選択されていません。"); return; }
    if (!editorText.trim()) { alert("プロンプト本文が空です。"); return; }

    const btn = elements.prompt.saveBtn;
    const originalBtnText = btn.textContent;
    btn.textContent = "保存中...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/save-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                promptId: selectedId,
                templateText: editorText
            })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert(result.message);
            // ストア内のデータを更新
            const index = state.promptStore.findIndex(p => p.id === selectedId);
            if (index !== -1) {
                state.promptStore[index].template_text = editorText;
            }
        } else {
            throw new Error(result.message || '不明なエラー');
        }

    } catch (error) {
        console.error("プロンプト保存エラー:", error);
        alert(`保存に失敗しました:\n${error.message}`);
    } finally {
        btn.textContent = originalBtnText;
        btn.disabled = false;
    }
}

/**
 * (C) 「削除」ボタンの処理
 */
async function handleDeletePrompt() {
    const selectedId = parseInt(elements.prompt.select.value, 10);
    const selectedName = elements.prompt.select.options[elements.prompt.select.selectedIndex].text;

    if (!selectedId) { alert("プロンプトが選択されていません。"); return; }
    if (!window.confirm(`本当にプロンプト「${selectedName}」を削除しますか？`)) return;
    
    const btn = elements.prompt.deleteBtn;
    btn.textContent = "削除中...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/delete-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ promptId: selectedId })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success') {
            alert(result.message);
            // ドロップダウンをリロードして削除を反映
            await loadPromptsIntoDropdown();
        } else {
            throw new Error(result.message || '不明なエラー');
        }

    } catch (error) {
        console.error("プロンプト削除エラー:", error);
        alert(`削除に失敗しました:\n${error.message}`);
    } finally {
        btn.textContent = "削除";
        btn.disabled = false;
    }
}
        
/**
 * (D) 「名前を付けて新規保存」ボタンの処理
 */
async function handleSaveAsNewPrompt() {
    const editorText = elements.prompt.editor.value;
    if (!editorText.trim()) { alert("プロンプト本文が空です。"); return; }

    const newName = window.prompt("新しいプロンプトの名前を入力してください:", "");
    if (!newName || !newName.trim()) { alert("名前がキャンセルされたか、空です。"); return; }

    const btn = elements.prompt.saveAsNewBtn;
    const originalBtnText = btn.textContent;
    btn.textContent = "保存中...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/save-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                promptId: null, // ID: null = 新規
                templateText: editorText,
                promptName: newName.trim()
            })
        });

        const result = await response.json();

        if (response.ok && result.status === 'success' && result.action === 'create') {
            alert(result.message);
            
            // ストアとドロップダウンを更新
            const newPrompt = result.new_prompt;
            state.promptStore.push(newPrompt); // ストアに追加
            
            const option = document.createElement('option');
            option.value = newPrompt.id;
            option.textContent = newPrompt.name;
            elements.prompt.select.appendChild(option);
            
            // 新しく作成したプロンプトを選択状態にする
            option.selected = true;
            elements.prompt.editor.value = newPrompt.template_text;
            
        } else {
            throw new Error(result.message || '不明なエラー');
        }

    } catch (error) {
        console.error("プロンプト新規保存エラー:", error);
        alert(`新規保存に失敗しました:\n${error.message}`);
    } finally {
        btn.textContent = originalBtnText;
        btn.disabled = false;
    }
}

/**
 * (E) ドロップダウン変更時にエディタの内容を更新
 */
function handleDropdownChange(e) {
    const selectedId = parseInt(e.target.value, 10);
    // JS内の「promptStore」から検索
    const selectedPrompt = state.promptStore.find(p => p.id === selectedId);
    
    if (selectedPrompt) {
        elements.prompt.editor.value = selectedPrompt.template_text;
    }
}