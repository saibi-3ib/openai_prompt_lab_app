// (★) これから作成する3つのモジュールから、初期化関数をインポート
import { initUiControls } from './uiControls.js';
import { initPostHandler } from './postHandler.js';
import { initPromptHandler } from './promptHandler.js';

// (★) DOMContentLoaded イベントで app を起動
document.addEventListener('DOMContentLoaded', () => {
    
    // --- 1. 状態 (State) ---
    // アプリケーション全体で共有する状態
    const state = {
        selectedPostIds: new Set(),
        lastClickedIndex: -1,
        promptStore: [],
        autolinker: new Autolinker({
            urls: { scheme: true, tld: true },
            email: false, phone: false, mention: 'twitter', hashtag: 'twitter',
            newWindow: true, stripPrefix: false, className: 'autolinked'
        })
    };

    // --- 2. 要素 (Elements) ---
    // すべてのDOM要素をここで一元管理
    const elements = {
        // 全体
        creditMonitor: document.getElementById('credit-monitor-display'),

        // フィルターペイン (UI Controls)
        filter: {
            wrapper: document.getElementById('filter-pane-wrapper'),
            toggleBtn: document.getElementById('filter-pane-toggle'),
            keywordInput: document.getElementById('filter-keyword'),
            likesInput: document.getElementById('filter-likes'),
            rtsInput: document.getElementById('filter-rts'),
            runBtn: document.getElementById('filter-run-btn'),
            resetBtn: document.getElementById('filter-reset-btn'),
            sentimentSelect: document.getElementById('filter-sentiment'),
        },
        
        // アカウント (UI Controls)
        accountFilter: {
            btn: document.getElementById('account-filter-btn'),
            label: document.getElementById('account-filter-label'),
            menu: document.getElementById('account-filter-menu'),
        },
        
        // セクター (UI Controls)
        sectorFilter: {
            btn: document.getElementById('sector-filter-btn'),
            menu: document.getElementById('sector-filter-menu'),
            label: document.getElementById('sector-filter-label'),
        },

        // ティッカー (UI Controls)
        tickerFilter: {
            input: document.getElementById('filter-ticker-input'),
            suggestions: document.getElementById('ticker-suggestions'),
            tagsContainer: document.getElementById('ticker-tags-container'),
        },

        // ポストペイン (Post Handler)
        post: {
            listContainer: document.getElementById('post-list-container'),
            selectionCounter: document.getElementById('selection-counter'),
            deselectAllBtn: document.getElementById('deselect-all-btn'),
        },

        // アクションペイン (Prompt/Post Handler)
        action: {
            wrapper: document.getElementById('action-pane-wrapper'),
            toggleBtn: document.getElementById('action-pane-toggle'),
            batchBtn: document.getElementById('analyze-batch-btn'),
            batchBtnCounter: document.getElementById('batch-btn-counter'),
            resultDisplay: document.getElementById('result-display'),
            modelSelect: document.getElementById('model-select'),
        },
        
        // プロンプト (Prompt Handler)
        prompt: {
            select: document.getElementById('prompt-select'),
            editor: document.getElementById('prompt-editor'),
            saveBtn: document.getElementById('save-prompt-btn'),
            saveAsNewBtn: document.getElementById('save-as-new-prompt-btn'),
            deleteBtn: document.getElementById('delete-prompt-btn'),
        }
    };

    // --- 3. 初期化 ---
    // 各モジュールを初期化し、必要な要素と状態を渡す (依存性の注入)
    try {
        initUiControls(elements, state);
        initPostHandler(elements, state);
        initPromptHandler(elements, state);
    } catch (error) {
        console.error("アプリケーションの初期化に失敗しました:", error);
    }
});