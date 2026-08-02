// main.js - Video Dubber Client Logic

// ─── Modern Toast Notification System ───────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
    if (!message) return;
    addNotification(message, type);
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-message toast-${type}`;

    let iconClass = 'fa-info-circle';
    if (type === 'success') iconClass = 'fa-circle-check';
    else if (type === 'error') iconClass = 'fa-circle-xmark';
    else if (type === 'warning') iconClass = 'fa-triangle-exclamation';

    toast.innerHTML = `
        <div class="toast-icon"><i class="fa-solid ${iconClass}"></i></div>
        <div class="toast-text">${message}</div>
        <div class="toast-close" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></div>
    `;

    container.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);

    const timer = setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 350);
    }, duration);

    toast.addEventListener('mouseenter', () => clearTimeout(timer));
}

// ─── Notification Icon Bar System ───────────────────────────────────────────
let notificationHistory = [];
let hasUnreadNotifications = false;

function toggleNotificationDropdown(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById('notificationDropdown');
    const dot = document.getElementById('notificationDot');
    if (!dropdown) return;

    const isHidden = dropdown.classList.contains('hidden');
    if (isHidden) {
        dropdown.classList.remove('hidden');
        if (dot) dot.style.display = 'none';
        hasUnreadNotifications = false;
    } else {
        dropdown.classList.add('hidden');
    }
}

function clearNotifications(event) {
    if (event) event.stopPropagation();
    notificationHistory = [];
    renderNotificationList();
    const dot = document.getElementById('notificationDot');
    if (dot) dot.style.display = 'none';
    hasUnreadNotifications = false;
}

function addNotification(message, type = 'info') {
    if (!message) return;

    // Filter out useless/transient routine messages from cluttering the notification bar
    const lowerStr = message.toLowerCase();
    if (
        lowerStr.includes('checking for update') ||
        lowerStr.includes('running the latest version') ||
        lowerStr.includes('up to date')
    ) {
        return;
    }

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    notificationHistory.unshift({ message, type, time: timeStr });
    if (notificationHistory.length > 30) notificationHistory.pop();

    const dropdown = document.getElementById('notificationDropdown');
    const isHidden = !dropdown || dropdown.classList.contains('hidden');
    if (isHidden) {
        hasUnreadNotifications = true;
        const dot = document.getElementById('notificationDot');
        if (dot) dot.style.display = 'block';
    }

    renderNotificationList();
}


function renderNotificationList() {
    const list = document.getElementById('notificationList');
    if (!list) return;

    if (notificationHistory.length === 0) {
        list.innerHTML = `
            <div class="notification-empty">
                <i class="fa-regular fa-bell-slash"></i>
                <p>No new notifications</p>
            </div>`;
        return;
    }

    list.innerHTML = notificationHistory.map(item => {
        let iconClass = 'fa-info-circle';
        if (item.type === 'success') iconClass = 'fa-circle-check';
        else if (item.type === 'error') iconClass = 'fa-circle-xmark';
        else if (item.type === 'warning') iconClass = 'fa-triangle-exclamation';

        return `
            <div class="notification-item type-${item.type}">
                <div class="notification-item-icon"><i class="fa-solid ${iconClass}"></i></div>
                <div class="notification-item-text">
                    <div>${item.message}</div>
                    <div class="notification-item-time">${item.time}</div>
                </div>
            </div>`;
    }).join('');
}

document.addEventListener('click', function(e) {
    const wrapper = document.querySelector('.notification-bar-wrapper');
    const dropdown = document.getElementById('notificationDropdown');
    if (dropdown && !dropdown.classList.contains('hidden')) {
        if (wrapper && !wrapper.contains(e.target)) {
            dropdown.classList.add('hidden');
        }
    }
});

// Global window.alert override so no native 127.0.0.1 / Win32 popup ever appears
try {
    Object.defineProperty(window, 'alert', {
        value: function(msg) {
            const text = String(msg || '');
            let type = 'info';
            const lower = text.toLowerCase();
            if (lower.includes('fail') || lower.includes('error') || lower.includes('cannot') || lower.includes('missing')) {
                type = 'error';
            } else if (lower.includes('success') || lower.includes('saved') || lower.includes('copied') || lower.includes('complete') || lower.includes('processed') || lower.includes('🎉')) {
                type = 'success';
            } else if (lower.includes('warning') || lower.includes('please') || lower.includes('choose')) {
                type = 'warning';
            }
            showToast(text, type);
        },
        writable: false,
        configurable: true
    });
} catch (e) {
    window.alert = function(msg) { showToast(String(msg || ''), 'info'); };
}

let supportedLanguages = {};
let relationshipPresets = {};
let currentJobId = null;
let currentJobData = null;
let eventSource = null;

document.addEventListener('DOMContentLoaded', () => {
    loadVoicesAndPresets();
    loadSystemFonts();
    initDropZone();
    initCustomPlayerControls();
    updateLivePreviewOverlays();
    initAutoSaveConfig();
    updateStartBatchBtnState();

    // Restore saved theme
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'light') {
        document.body.classList.add('light-theme');
        updateThemeUI(true);
    }
});

async function initAutoSaveConfig() {
    const keyInput = document.getElementById('geminiApiKeyInput');
    const modelSelect = document.getElementById('geminiModelSelect');
    const groqKeyInput = document.getElementById('groqApiKeyInput');
    const deepseekKeyInput = document.getElementById('deepseekApiKeyInput');
    const openrouterKeyInput = document.getElementById('openrouterApiKeyInput');
    const openaiKeyInput = document.getElementById('openaiApiKeyInput');

    let savedKey = localStorage.getItem('gemini_api_key') || '';
    let savedModel = localStorage.getItem('gemini_model') || '';
    let savedGroqKey = localStorage.getItem('groq_api_key') || '';
    let savedDeepseekKey = localStorage.getItem('deepseek_api_key') || '';
    let savedOpenrouterKey = localStorage.getItem('openrouter_api_key') || '';
    let savedOpenaiKey = localStorage.getItem('openai_api_key') || '';

    try {
        const res = await fetch('/api/config');
        const cfg = await res.json();
        if (cfg.gemini_api_key) savedKey = cfg.gemini_api_key;
        if (cfg.gemini_model) savedModel = cfg.gemini_model;
        if (cfg.groq_api_key) savedGroqKey = cfg.groq_api_key;
        if (cfg.deepseek_api_key) savedDeepseekKey = cfg.deepseek_api_key;
        if (cfg.openrouter_api_key) savedOpenrouterKey = cfg.openrouter_api_key;
        if (cfg.openai_api_key) savedOpenaiKey = cfg.openai_api_key;
    } catch (e) {
        console.warn('Failed to fetch backend config:', e);
    }

    if (keyInput && savedKey) {
        keyInput.value = savedKey;
        localStorage.setItem('gemini_api_key', savedKey);
    }
    if (modelSelect && savedModel) {
        modelSelect.value = savedModel;
        localStorage.setItem('gemini_model', savedModel);
    }
    if (groqKeyInput && savedGroqKey) {
        groqKeyInput.value = savedGroqKey;
        localStorage.setItem('groq_api_key', savedGroqKey);
    }
    if (deepseekKeyInput && savedDeepseekKey) {
        deepseekKeyInput.value = savedDeepseekKey;
        localStorage.setItem('deepseek_api_key', savedDeepseekKey);
    }
    if (openrouterKeyInput && savedOpenrouterKey) {
        openrouterKeyInput.value = savedOpenrouterKey;
        localStorage.setItem('openrouter_api_key', savedOpenrouterKey);
    }
    if (openaiKeyInput && savedOpenaiKey) {
        openaiKeyInput.value = savedOpenaiKey;
        localStorage.setItem('openai_api_key', savedOpenaiKey);
    }

    // Auto-save on every keystroke (debounced 500ms)
    if (keyInput) {
        keyInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            localStorage.setItem('gemini_api_key', val);
            autoSaveBackendConfig({ gemini_api_key: val });
        });
    }
    if (modelSelect) {
        modelSelect.addEventListener('change', (e) => {
            const val = e.target.value;
            localStorage.setItem('gemini_model', val);
            autoSaveBackendConfig({ gemini_model: val });
        });
    }
    if (groqKeyInput) {
        groqKeyInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            localStorage.setItem('groq_api_key', val);
            autoSaveBackendConfig({ groq_api_key: val });
        });
    }
    if (deepseekKeyInput) {
        deepseekKeyInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            localStorage.setItem('deepseek_api_key', val);
            autoSaveBackendConfig({ deepseek_api_key: val });
        });
    }
    if (openrouterKeyInput) {
        openrouterKeyInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            localStorage.setItem('openrouter_api_key', val);
            autoSaveBackendConfig({ openrouter_api_key: val });
        });
    }
    if (openaiKeyInput) {
        openaiKeyInput.addEventListener('input', (e) => {
            const val = e.target.value.trim();
            localStorage.setItem('openai_api_key', val);
            autoSaveBackendConfig({ openai_api_key: val });
        });
    }
    // Primary AI model selector
    const primaryAiSel = document.getElementById('primaryAiModelSelect');
    if (primaryAiSel) {
        primaryAiSel.addEventListener('change', (e) => {
            const val = e.target.value;
            localStorage.setItem('primary_ai_model', val);
            autoSaveBackendConfig({ primary_ai_model: val });
            onPrimaryAiModelChange(val);
        });
    }
}

let autoSaveTimer = null;
function autoSaveBackendConfig(data) {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => {
        fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).catch(e => console.warn('Config auto-save error:', e));
    }, 500);
}

function onPrimaryAiModelChange(val) {
    const hint = document.getElementById('primaryAiModelHint');
    if (hint) hint.textContent = '✨ Gemini API will be used for AI translation.';
}

function toggleTheme() {
    const isLight = document.body.classList.toggle('light-theme');
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
    updateThemeUI(isLight);
}

function updateThemeUI(isLight) {
    const icon = document.getElementById('themeToggleIcon');
    const text = document.getElementById('themeToggleText');
    if (icon) {
        icon.className = isLight ? 'fa-solid fa-moon' : 'fa-solid fa-sun';
    }
    if (text) {
        text.textContent = isLight ? 'Dark' : 'Light';
    }
}

function toggleIntroOutroInputs() {
    const introCheck = document.getElementById('introSpeechCheck');
    const introInput = document.getElementById('introSpeechInput');
    const outroCheck = document.getElementById('outroSpeechCheck');
    const outroInput = document.getElementById('outroSpeechInput');

    if (introInput && introCheck) {
        introInput.disabled = !introCheck.checked;
    }
    if (outroInput && outroCheck) {
        outroInput.disabled = !outroCheck.checked;
    }
}

function applyTheme(themeName) {
    document.documentElement.removeAttribute('data-theme');
    document.body.removeAttribute('data-theme');
    localStorage.removeItem('app_theme');
}

function toggleTheme() {
    applyTheme('dark');
}

function initTheme() {
    applyTheme('dark');
}

// Initialize theme immediately
initTheme();

function savePreferences() {
    const themeSel = document.getElementById('themeSelect');
    if (themeSel) {
        applyTheme(themeSel.value);
    }

    const groqKeyInput = document.getElementById('groqApiKeyInput');
    if (groqKeyInput) {
        localStorage.setItem('groq_api_key', groqKeyInput.value.trim());
    }

    const deepseekKeyInput = document.getElementById('deepseekApiKeyInput');
    if (deepseekKeyInput) {
        localStorage.setItem('deepseek_api_key', deepseekKeyInput.value.trim());
    }

    const openrouterKeyInput = document.getElementById('openrouterApiKeyInput');
    if (openrouterKeyInput) {
        localStorage.setItem('openrouter_api_key', openrouterKeyInput.value.trim());
    }

    const openaiKeyInput = document.getElementById('openaiApiKeyInput');
    if (openaiKeyInput) {
        localStorage.setItem('openai_api_key', openaiKeyInput.value.trim());
    }

    const primaryAiSelect = document.getElementById('primaryAiModelSelect');
    if (primaryAiSelect) {
        localStorage.setItem('primary_ai_model', primaryAiSelect.value);
        autoSaveBackendConfig({ primary_ai_model: primaryAiSelect.value });
    }

    const introCheck = document.getElementById('introSpeechCheck');
    const introInput = document.getElementById('introSpeechInput');
    const outroCheck = document.getElementById('outroSpeechCheck');
    const outroInput = document.getElementById('outroSpeechInput');

    if (introCheck && introInput) {
        localStorage.setItem('intro_speech_enabled', introCheck.checked ? 'true' : 'false');
        localStorage.setItem('intro_speech_text', introInput.value.trim());
    }
    if (outroCheck && outroInput) {
        localStorage.setItem('outro_speech_enabled', outroCheck.checked ? 'true' : 'false');
        localStorage.setItem('outro_speech_text', outroInput.value.trim());
    }

    const saveSrtToggle = document.getElementById('prefSaveSrtToggle');
    if (saveSrtToggle) {
        const isEnabled = saveSrtToggle.checked;
        localStorage.setItem('save_srt_enabled', isEnabled ? 'true' : 'false');
        if (typeof autoSaveBackendConfig === 'function') {
            autoSaveBackendConfig({ save_srt: isEnabled });
        }
    }

    const concurrentSelect = document.getElementById('prefConcurrentBatchSelect');
    if (concurrentSelect) {
        localStorage.setItem('concurrent_batch_limit', concurrentSelect.value);
    }

    closePreferencesModal();
    if (typeof showToast === 'function') {
        showToast('Preferences saved successfully!', 'success');
    }
}

function loadPreferences() {
    const themeSel = document.getElementById('themeSelect');
    if (themeSel) {
        themeSel.value = localStorage.getItem('app_theme') || 'dark';
    }

    const groqKeyInput = document.getElementById('groqApiKeyInput');
    if (groqKeyInput) {
        groqKeyInput.value = localStorage.getItem('groq_api_key') || '';
    }

    const deepseekKeyInput = document.getElementById('deepseekApiKeyInput');
    if (deepseekKeyInput) {
        deepseekKeyInput.value = localStorage.getItem('deepseek_api_key') || '';
    }

    const openrouterKeyInput = document.getElementById('openrouterApiKeyInput');
    if (openrouterKeyInput) {
        openrouterKeyInput.value = localStorage.getItem('openrouter_api_key') || '';
    }

    const openaiKeyInput = document.getElementById('openaiApiKeyInput');
    if (openaiKeyInput) {
        openaiKeyInput.value = localStorage.getItem('openai_api_key') || '';
    }

    const primaryAiSelect = document.getElementById('primaryAiModelSelect');
    if (primaryAiSelect) {
        const saved = localStorage.getItem('primary_ai_model') || 'gemini';
        primaryAiSelect.value = saved;
        onPrimaryAiModelChange(saved);
    }

    const introCheck = document.getElementById('introSpeechCheck');
    const introInput = document.getElementById('introSpeechInput');
    const outroCheck = document.getElementById('outroSpeechCheck');
    const outroInput = document.getElementById('outroSpeechInput');

    if (introCheck && introInput) {
        introCheck.checked = (localStorage.getItem('intro_speech_enabled') === 'true');
        introInput.value = localStorage.getItem('intro_speech_text') || '';
    }
    if (outroCheck && outroInput) {
        outroCheck.checked = (localStorage.getItem('outro_speech_enabled') === 'true');
        outroInput.value = localStorage.getItem('outro_speech_text') || '';
    }
    toggleIntroOutroInputs();

    const saveSrtToggle = document.getElementById('prefSaveSrtToggle');
    if (saveSrtToggle) {
        const savedVal = localStorage.getItem('save_srt_enabled');
        saveSrtToggle.checked = (savedVal === null || savedVal === 'true');
    }

    const concurrentSelect = document.getElementById('prefConcurrentBatchSelect');
    if (concurrentSelect) {
        concurrentSelect.value = localStorage.getItem('concurrent_batch_limit') || '1';
    }
}

function switchPrefTab(tabId) {
    const tabs = ['workflow', 'engines', 'voices', 'voiceConfig', 'introOutro', 'audio', 'theme', 'logs'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tabBtn${t.charAt(0).toUpperCase() + t.slice(1)}`);
        const panel = document.getElementById(`prefPanel${t.charAt(0).toUpperCase() + t.slice(1)}`);
        if (btn) btn.classList.remove('active');
        if (panel) {
            panel.classList.add('hidden');
            panel.classList.remove('active');
        }
    });

    const targetKey = tabId.charAt(0).toUpperCase() + tabId.slice(1);
    const activeBtn = document.getElementById(`tabBtn${targetKey}`);
    const activePanel = document.getElementById(`prefPanel${targetKey}`);
    if (activeBtn) activeBtn.classList.add('active');
    if (activePanel) {
        activePanel.classList.remove('hidden');
        activePanel.classList.add('active');
    }

    // Auto-refresh model list when entering Voice Config tab
    if (tabId === 'voiceConfig') {
        refreshVoiceConfigModels();
    } else if (tabId === 'logs') {
        const consoleEl = document.getElementById('activityLogConsole');
        if (consoleEl) consoleEl.scrollTop = consoleEl.scrollHeight;
    }
}

function openPreferencesModal() {
    loadPreferences();
    switchPrefTab('workflow');
    document.getElementById('preferencesModal').classList.remove('hidden');
}

function closePreferencesModal() {
    document.getElementById('preferencesModal').classList.add('hidden');
}

// Close modal when clicking on backdrop
window.addEventListener('click', (e) => {
    const modal = document.getElementById('preferencesModal');
    if (e.target === modal) {
        closePreferencesModal();
    }
});

// 1b. Load real installed fonts (bundled + Windows Fonts) and wire the preview to use the
// exact same files ffmpeg will burn in — no more hardcoded 4-option list, and no more
// separate "guess a Google Font" path for preview vs "guess a Windows folder" path for render.
async function loadSystemFonts() {
    const subFont = document.getElementById('subFont');
    const textFont = document.getElementById('textFont');
    if (!subFont && !textFont) return;

    try {
        const res = await fetch('/api/fonts');
        const data = await res.json();
        const fonts = (data && data.fonts) || [];
        if (fonts.length === 0) return;

        // Register a @font-face per font, pointing at the exact file path — the SAME path
        // that gets sent back to the server and passed to ffmpeg's drawtext fontfile=.
        let styleEl = document.getElementById('dynamicFontFaces');
        if (!styleEl) {
            styleEl = document.createElement('style');
            styleEl.id = 'dynamicFontFaces';
            document.head.appendChild(styleEl);
        }
        styleEl.textContent = fonts.map(f => {
            const safeFamily = f.name.replace(/"/g, '\\"');
            const url = '/api/font-file?path=' + encodeURIComponent(f.path);
            return `@font-face { font-family: "${safeFamily}"; src: local("${safeFamily}"), url("${url}"); font-display: block; }`;
        }).join('\n');

        const populate = (selectEl) => {
            if (!selectEl) return;
            const previousValue = selectEl.value;
            selectEl.innerHTML = '';
            fonts.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.name;
                opt.dataset.path = f.path;
                opt.textContent = f.name;
                selectEl.appendChild(opt);
            });
            const match = fonts.find(f => f.name === previousValue);
            const kantumruy = fonts.find(f => f.name === 'Kantumruy Pro');
            const defaultFont = kantumruy ? kantumruy.name : fonts[0].name;
            selectEl.value = match ? previousValue : defaultFont;

            const loadAndApplyFont = () => {
                const fontInfo = getSelectedFont(selectEl.id);
                if (fontInfo && fontInfo.name && fontInfo.path && window.FontFace) {
                    const url = '/api/font-file?path=' + encodeURIComponent(fontInfo.path);
                    const ff = new FontFace(fontInfo.name, `url("${url}")`);
                    ff.load().then(loaded => {
                        document.fonts.add(loaded);
                        updateLivePreviewOverlays();
                    }).catch(err => {
                        console.warn('FontFace preloader warning for', fontInfo.name, err);
                        updateLivePreviewOverlays();
                    });
                } else {
                    updateLivePreviewOverlays();
                }
            };

            selectEl.onchange = loadAndApplyFont;
            selectEl.oninput = loadAndApplyFont;
        };

        populate(subFont);
        populate(textFont);
        updateLivePreviewOverlays();
    } catch (e) {
        console.warn('Could not load system fonts, keeping default font list:', e);
    }
}

// Given a font <select>, returns { name, path } for the selected option — path is the exact
// file on disk that /api/fonts reported, so the same value can be sent to the backend and
// resolved to the identical file ffmpeg burns in.
function getSelectedFont(selectId) {
    const el = document.getElementById(selectId);
    if (!el || !el.selectedOptions || !el.selectedOptions[0]) {
        return { name: 'Kantumruy Pro', path: '' };
    }
    const opt = el.selectedOptions[0];
    return { name: opt.value, path: opt.dataset.path || '' };
}

// 1. Load Supported Languages, Voices & Relationship Presets
function onRvcToggleChange() {
    const toggle = document.getElementById('rvcToggle');
    const group  = document.getElementById('rvcControlsGroup');
    if (!toggle || !group) return;

    if (toggle.checked) {
        group.style.opacity = '1.0';
        group.style.pointerEvents = 'auto';
    } else {
        group.style.opacity = '0.4';
        group.style.pointerEvents = 'none';
    }
}

async function loadRvcModels() {
    try {
        const res = await fetch('/api/rvc_models');
        const data = await res.json();
        const select = document.getElementById('rvcModelSelect');
        const toggle = document.getElementById('rvcToggle');
        if (!select) return;

        select.innerHTML = '';
        if (data.models && Array.isArray(data.models) && data.models.length > 0) {
            const hasMale = data.models.some(m => m.usable && m.gender === 'Male');
            const hasFemale = data.models.some(m => m.usable && m.gender === 'Female');

            // Auto Gender Match: RVC picks a Male/Female cloned voice per
            // segment automatically, the same way Edge TTS already does.
            // Works with just one gender tagged (the other gender's
            // segments fall back to it), but needs at least one.
            if (hasMale || hasFemale) {
                const autoOpt = document.createElement('option');
                autoOpt.value = 'auto_gender_match';
                const label = (hasMale && hasFemale)
                    ? '🎭 Auto (Match Gender per Segment)'
                    : `🎭 Auto (Match Gender per Segment) — only ${hasMale ? 'Male' : 'Female'} tagged`;
                autoOpt.textContent = label;
                select.appendChild(autoOpt);
            }

            const prefIdx = data.models.findIndex(m => m.filename.toLowerCase().includes('tmppdg4godj'));
            const targetIdx = prefIdx >= 0 ? prefIdx : 0;

            data.models.forEach((m, idx) => {
                const opt = document.createElement('option');
                opt.value = m.filename;
                const genderTag = m.gender && m.gender !== 'Unknown' ? ` [${m.gender}]` : '';
                opt.textContent = `🎙️ ${m.name}${genderTag} (${m.size_mb} MB)`;
                if (!(hasMale || hasFemale) && idx === targetIdx) opt.selected = true;
                select.appendChild(opt);
            });
            if (typeof onRvcToggleChange === 'function') onRvcToggleChange();
            if (typeof onRvcModelSelectChange === 'function') onRvcModelSelectChange(select);
        } else {
            select.innerHTML = '<option value="none" selected>No RVC Models (.pth) Found</option>';
            if (toggle) {
                toggle.checked = false;
                onRvcToggleChange();
            }
        }
    } catch (e) {
        console.warn('Failed to load RVC models:', e);
    }
}

function triggerRvcUpload() {
    const input = document.getElementById('rvcFileInput');
    if (input) input.click();
}

async function handleRvcFileUpload(input) {
    if (!input || !input.files || !input.files[0]) return;
    const file = input.files[0];
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/upload_rvc_model', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.status === 'success') {
            alert(`RVC Model '${data.filename}' uploaded successfully!`);
            await loadRvcModels();
            const select = document.getElementById('rvcModelSelect');
            if (select) select.value = data.filename;
            const toggle = document.getElementById('rvcToggle');
            if (toggle) {
                toggle.checked = true;
                onRvcToggleChange();
            }
        } else {
            alert(`Upload failed: ${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Upload error: ${e.message}`);
    }
}


// ─── Voice Config Tab Functions ───────────────────────────────────────────────

function triggerVoiceConfigUpload() {
    const input = document.getElementById('vcRvcFileInput');
    if (input) input.click();
}

async function handleVoiceConfigRvcUpload(input) {
    if (!input || !input.files || !input.files[0]) return;
    const file = input.files[0];

    const statusEl = document.getElementById('vcUploadStatus');
    const showStatus = (msg, cls) => {
        if (!statusEl) return;
        statusEl.className = `vc-upload-status ${cls}`;
        statusEl.style.display = 'flex';
        statusEl.innerHTML = msg;
    };

    const isAudio = /\.(mp3|wav|flac|m4a|ogg|aac)$/i.test(file.name);
    if (isAudio) {
        showStatus('<i class="fa-solid fa-spinner fa-spin"></i> Analyzing audio &amp; auto-cloning voice in background... Creating .pth &amp; .index models...', 'uploading');
    } else {
        showStatus('<i class="fa-solid fa-spinner fa-spin"></i> Uploading model file...', 'uploading');
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('gender', 'auto');

    try {
        const res = await fetch('/api/upload_rvc_model', { method: 'POST', body: formData });
        const data = await res.json();

        if (data.status === 'success' || data.status === 'cloned') {
            const successMsg = data.message || `<strong>${data.filename}</strong> uploaded successfully!`;
            showStatus(`<i class="fa-solid fa-circle-check"></i> ${successMsg}`, 'success');
            // Refresh both the Voice Config list AND the rvcModelSelect dropdown
            await loadRvcModels();
            renderVoiceConfigModels(data.models || []);
            // Auto-select the new model in Language & Voices tab
            const select = document.getElementById('rvcModelSelect');
            if (select) select.value = data.filename;
            // Auto-enable RVC toggle
            const toggle = document.getElementById('rvcToggle');
            if (toggle && !toggle.checked) {
                toggle.checked = true;
                onRvcToggleChange();
            }
            setTimeout(() => { if (statusEl) statusEl.style.display = 'none'; }, 6000);
        } else {
            showStatus(`<i class="fa-solid fa-circle-xmark"></i> Upload failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (e) {
        showStatus(`<i class="fa-solid fa-circle-xmark"></i> Upload error: ${e.message}`, 'error');
    }
    // Reset input so the same file can be re-uploaded if needed
    input.value = '';
}

async function refreshVoiceConfigModels() {
    try {
        const res = await fetch('/api/rvc_models');
        const data = await res.json();
        renderVoiceConfigModels(data.models || []);
    } catch (e) {
        console.warn('Failed to refresh Voice Config models:', e);
    }
}

function renderVoiceConfigModels(models) {
    const listEl = document.getElementById('vcModelsList');
    const emptyEl = document.getElementById('vcModelsEmpty');
    if (!listEl) return;

    // Remove all existing model cards (keep empty placeholder)
    Array.from(listEl.querySelectorAll('.vc-model-card')).forEach(c => c.remove());

    if (!models || models.length === 0) {
        if (emptyEl) emptyEl.style.display = 'flex';
        return;
    }
    if (emptyEl) emptyEl.style.display = 'none';

    models.forEach(m => {
        const card = document.createElement('div');
        card.className = 'vc-model-card';
        card.dataset.filename = m.filename;
        card.dataset.modelName = m.name;

        const indexBadge = m.has_index
            ? '<span class="vc-model-badge has-index"><i class="fa-solid fa-circle-check"></i> Index</span>'
            : '<span class="vc-model-badge no-index"><i class="fa-solid fa-triangle-exclamation"></i> No Index</span>';

        const genderVal = m.gender || 'Unknown';
        const genderClass = genderVal === 'Female' ? 'vc-icon-female' : (genderVal === 'Male' ? 'vc-icon-male' : 'vc-icon-unknown');
        const genderPicker = `
            <select class="vc-gender-select vc-gender-${genderVal.toLowerCase()}" title="Click to change model gender"
                    onchange="updateVoiceModelGender('${m.filename}', this.value)">
                <option value="Female" ${genderVal === 'Female' ? 'selected' : ''}>♀ Female</option>
                <option value="Male" ${genderVal === 'Male' ? 'selected' : ''}>♂ Male</option>
                <option value="Unknown" ${genderVal === 'Unknown' ? 'selected' : ''}>⚧ Untagged</option>
            </select>`;

        card.innerHTML = `
            <div class="vc-model-info">
                <div class="vc-model-icon ${genderClass}"><i class="fa-solid fa-microphone-lines"></i></div>
                <div class="vc-model-meta">
                    <div class="vc-name-display" id="vcNameDisplay_${m.filename}">
                        <span class="vc-model-name" title="${m.filename}">${m.name}</span>
                        <button class="vc-edit-name-btn" onclick="startEditVoiceModelName('${m.filename}')" title="Rename model">
                            <i class="fa-solid fa-pen-to-square"></i>
                        </button>
                    </div>
                    <div class="vc-name-edit hidden" id="vcNameEdit_${m.filename}">
                        <input type="text" class="vc-name-input" id="vcNameInput_${m.filename}"
                               value="${m.name}" placeholder="Enter model name"
                               onkeydown="if(event.key==='Enter')saveVoiceModelName('${m.filename}'); if(event.key==='Escape')cancelEditVoiceModelName('${m.filename}');">
                        <div class="vc-name-edit-actions">
                            <button class="vc-save-name-btn" onclick="saveVoiceModelName('${m.filename}')" title="Save name">
                                <i class="fa-solid fa-check"></i>
                            </button>
                            <button class="vc-cancel-name-btn" onclick="cancelEditVoiceModelName('${m.filename}')" title="Cancel">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                        </div>
                    </div>
                    <div class="vc-model-details">
                        <span>${m.size_mb} MB</span>
                        ${indexBadge}
                        ${genderPicker}
                    </div>
                </div>
            </div>
            <div class="vc-model-actions">
                <button class="vc-preview-btn" id="vcPreviewBtn_${m.filename}"
                        onclick="previewVoiceConfigModel('${m.filename}', this)" title="Preview voice">
                    <i class="fa-solid fa-volume-high"></i>
                </button>
                <button class="vc-delete-btn" onclick="deleteVoiceConfigModel('${m.filename}')" title="Delete model">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;
        listEl.appendChild(card);
    });
}

async function updateVoiceModelGender(filename, gender) {
    try {
        const res = await fetch('/api/set_rvc_model_gender', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, gender })
        });
        const data = await res.json();
        if (data.status === 'tagged') {
            if (typeof showToast === 'function') showToast(`Tagged "${filename}" as ${data.gender}`, 'success');
            // Refresh both lists so the Auto Gender Match option in
            // Language & Voices reflects the new tag immediately.
            await loadRvcModels();
            renderVoiceConfigModels(data.models || []);
        } else {
            alert(`Failed to tag gender: ${data.error || 'Unknown error'}`);
            await refreshVoiceConfigModels();
        }
    } catch (e) {
        alert(`Gender tagging error: ${e.message}`);
        await refreshVoiceConfigModels();
    }
}

async function previewVoiceConfigModel(filename, btn) {
    // Stop any playing preview
    if (window.currentAudioPreview) {
        window.currentAudioPreview.pause();
        window.currentAudioPreview = null;
    }
    // Reset all preview buttons to idle state
    document.querySelectorAll('.vc-preview-btn').forEach(b => {
        b.disabled = false;
        b.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
        b.classList.remove('playing');
    });

    if (!btn) btn = document.getElementById(`vcPreviewBtn_${filename}`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    }

    try {
        const res = await fetch('/api/preview_rvc_with_sample', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rvc_model: filename,
                rvc_pitch: 0
            })
        });
        const data = await res.json();
        if (data.ok && data.audio) {
            const audio = new Audio(data.audio);
            window.currentAudioPreview = audio;
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-stop"></i>';
                btn.classList.add('playing');
                btn.onclick = () => {
                    audio.pause();
                    btn.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
                    btn.classList.remove('playing');
                    btn.onclick = () => previewVoiceConfigModel(filename, btn);
                };
            }
            audio.onended = () => {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
                    btn.classList.remove('playing');
                    btn.onclick = () => previewVoiceConfigModel(filename, btn);
                }
            };
            await audio.play();
        } else {
            alert(`Preview failed: ${data.error || 'Unknown error'}`);
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-volume-high"></i>'; }
        }
    } catch (e) {
        alert(`Preview error: ${e.message}`);
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-volume-high"></i>'; }
    }
}

function startEditVoiceModelName(filename) {
    const displayEl = document.getElementById(`vcNameDisplay_${filename}`);
    const editEl    = document.getElementById(`vcNameEdit_${filename}`);
    const inputEl   = document.getElementById(`vcNameInput_${filename}`);
    if (!displayEl || !editEl) return;
    displayEl.classList.add('hidden');
    editEl.classList.remove('hidden');
    if (inputEl) { inputEl.focus(); inputEl.select(); }
}

function cancelEditVoiceModelName(filename) {
    const displayEl = document.getElementById(`vcNameDisplay_${filename}`);
    const editEl    = document.getElementById(`vcNameEdit_${filename}`);
    if (!displayEl || !editEl) return;
    editEl.classList.add('hidden');
    displayEl.classList.remove('hidden');
}

async function saveVoiceModelName(filename) {
    const inputEl = document.getElementById(`vcNameInput_${filename}`);
    if (!inputEl) return;
    const newName = inputEl.value.trim();
    if (!newName) { inputEl.focus(); return; }

    // Derive new filename: keep extension, replace base with sanitised name
    const ext = filename.slice(filename.lastIndexOf('.'));            // '.pth'
    const newFilename = newName.replace(/[\\/:*?"<>|]/g, '_') + ext; // safe filename

    try {
        const res = await fetch('/api/rename_rvc_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_filename: filename, new_filename: newFilename })
        });
        const data = await res.json();
        if (data.status === 'renamed') {
            // Refresh both lists in sync
            await loadRvcModels();
            renderVoiceConfigModels(data.models || []);
            if (typeof showToast === 'function') showToast(`Renamed to "${newName}"`, 'success');
        } else {
            alert(`Rename failed: ${data.error || 'Unknown error'}`);
            cancelEditVoiceModelName(filename);
        }
    } catch (e) {
        alert(`Rename error: ${e.message}`);
        cancelEditVoiceModelName(filename);
    }
}

async function deleteVoiceConfigModel(filename) {
    const confirmed = await showCustomConfirm(
        "Delete Voice Model",
        `Are you sure you want to delete RVC model "${filename}"? This will also remove its paired .index file if present.`,
        { confirmText: "Yes, Delete", cancelText: "Cancel", isDanger: true }
    );
    if (!confirmed) return;

    try {
        const res = await fetch('/api/delete_rvc_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename })
        });
        const data = await res.json();
        if (data.status === 'deleted') {
            const card = document.querySelector(`.vc-model-card[data-filename="${filename}"]`);
            if (card) {
                card.style.transition = 'opacity 0.2s, transform 0.2s';
                card.style.opacity = '0';
                card.style.transform = 'translateX(16px)';
                setTimeout(() => card.remove(), 220);
            }
            await loadRvcModels();
            renderVoiceConfigModels(data.models || []);
            showToast(`Model "${filename}" deleted successfully.`, 'success');
        } else {
            showToast(`Delete failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (e) {
        showToast(`Delete error: ${e.message}`, 'error');
    }
}



async function loadVoicesAndPresets() {
    try {
        const response = await fetch('/api/voices');

        const data = await response.json();
        supportedLanguages = data.languages || {};
        relationshipPresets = data.relationship_presets || {};

        // Cache voices by language code for per-segment gender resolution
        window._voicesByLang = {};
        for (const [code, info] of Object.entries(supportedLanguages)) {
            window._voicesByLang[code] = info.voices || [];
        }

        // Populate Languages
        const langSelect = document.getElementById('targetLangSelect');
        langSelect.innerHTML = '';

        for (const [code, info] of Object.entries(supportedLanguages)) {
            const opt = document.createElement('option');
            opt.value = code;
            opt.textContent = info.name;
            if (code === 'km') opt.selected = true;
            langSelect.appendChild(opt);
        }

        onLanguageChange();
        await loadRvcModels();
    } catch (err) {
        console.error('Failed to load voices:', err);
    }
}


// Update voice selector options when selected language changes
function onLanguageChange() {
    const langCode = document.getElementById('targetLangSelect').value;
    const voiceSelect = document.getElementById('voiceSelect');
    voiceSelect.innerHTML = '';

    // First option: Auto Detect Gender (always present)
    const autoOpt = document.createElement('option');
    autoOpt.value = 'auto';
    autoOpt.textContent = '🤖 Auto Detect Gender';
    autoOpt.selected = true;
    voiceSelect.appendChild(autoOpt);

    if (supportedLanguages[langCode] && supportedLanguages[langCode].voices) {
        supportedLanguages[langCode].voices.forEach(voice => {
            const opt = document.createElement('option');
            opt.value = voice.id;
            const genderIcon = voice.gender === 'Female' ? '👩' : '👨';
            opt.textContent = `${genderIcon} ${voice.name}`;
            voiceSelect.appendChild(opt);
        });
    }
}

// Drop Zone Setup — video player panel IS the drop zone
function initDropZone() {
    const dropZone = document.getElementById('videoDropZone');
    const fileInput = document.getElementById('videoFileInput');

    if (!dropZone) return;

    // Double-click on placeholder or panel → open file browser
    dropZone.addEventListener('dblclick', (e) => {
        if (e.target.closest('video')) return;
        fileInput.click();
    });

    // Single click anywhere on the drop zone → open file browser (unless clicking video, button or label)
    dropZone.addEventListener('click', (e) => {
        if (e.target.closest('video')) return;
        if (e.target.closest('button')) return;
        if (e.target.closest('label')) return;  // label already triggers the input natively
        const player = document.getElementById('outputVideoPlayer');
        if (player.classList.contains('hidden')) {
            fileInput.click();
        }
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', (e) => {
        if (!dropZone.contains(e.relatedTarget)) {
            dropZone.classList.remove('dragover');
        }
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            // Manually set files on the input
            const dt = new DataTransfer();
            dt.items.add(e.dataTransfer.files[0]);
            fileInput.files = dt.files;
            updateFileInfo();
        }
    });

    fileInput.addEventListener('change', updateFileInfo);
}

let loadedVideoFile = null;

function updateFileInfo() {
    const fileInput = document.getElementById('videoFileInput');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const placeholder = document.getElementById('videoPlaceholder');
    const player = document.getElementById('outputVideoPlayer');
    const badge = document.getElementById('playerStatusBadge');
    const clearBtn = document.getElementById('clearBtn');
    const overlayClose = document.getElementById('videoOverlayClose');

    if (fileInput && fileInput.files && fileInput.files.length > 0) {
        const file = fileInput.files[0];
        loadedVideoFile = file;
        
        if (fileName) fileName.textContent = file.name;
        if (fileInfo) fileInfo.classList.remove('hidden');
        if (clearBtn) clearBtn.classList.remove('hidden');
        if (overlayClose) overlayClose.classList.remove('hidden');

        const dropZone = document.getElementById('videoDropZone');
        if (dropZone) dropZone.classList.add('has-video');

        // Hide placeholder, show player
        if (placeholder) placeholder.classList.add('hidden');
        if (player) player.classList.remove('hidden');

        // Update badge
        if (badge) {
            badge.innerHTML = '<i class="fa-solid fa-circle-check"></i> Video Loaded';
            badge.className = 'badge badge-success';
        }

        // Load video into player for immediate preview
        try {
            const videoURL = URL.createObjectURL(file);
            if (player) {
                // IMPORTANT: never set `player.src` directly. This <video> element uses a
                // <source id="videoSource"> child everywhere else (showStudioSection() after
                // render, switchAudioTrack()). Per the HTML5 spec, once a <video> has its own
                // `src` attribute set, the browser permanently ignores <source> children for
                // that element -- so later attempts to swap in the dubbed output via
                // videoSource.src would silently no-op and the player would keep showing this
                // original file forever. Route through the <source> child instead, and make
                // sure no stale direct `src` attribute is lingering from a previous session.
                player.removeAttribute('src');
                const videoSourceEl = document.getElementById('videoSource');
                if (videoSourceEl) videoSourceEl.src = videoURL;
                player.load();

                // Once metadata loads, resize the container to fit the video's aspect ratio
                player.onloadedmetadata = () => resizeDropZoneToVideo(player);
                player.onloadeddata = () => resizeDropZoneToVideo(player);
            }
        } catch (e) {
            console.error('Preview load error:', e);
        }

        // Refresh live preview overlays state
        updateLivePreviewOverlays();

        // Unlock the Transcript button now that a video is loaded
        const processBtn = document.getElementById('unifiedProcessBtn');
        if (processBtn) {
            processBtn.disabled = false;
            processBtn.style.opacity = '1';
            processBtn.style.cursor = 'pointer';
            processBtn.style.pointerEvents = 'auto';
        }
    }
}

function resizeDropZoneToVideo(player) {
    const dropZone = document.getElementById('videoDropZone');
    const controls = document.getElementById('playerControls');
    if (!dropZone) return;
    dropZone.style.width = '';   // clear any inline width so CSS fit-content takes over
    dropZone.classList.add('has-video');

    if (controls && player) {
        let calcWidth = 0;
        if (player.videoWidth && player.videoHeight) {
            calcWidth = Math.round((player.videoWidth / player.videoHeight) * 552);
        } else {
            calcWidth = Math.round(player.getBoundingClientRect().width);
        }

        if (calcWidth > 0) {
            controls.style.width = calcWidth + 'px';
            controls.style.maxWidth = calcWidth + 'px';
        }
    }
}

function clearVideoPreview() {
    loadedVideoFile = null;
    const fileInput = document.getElementById('videoFileInput');
    const fileInfo = document.getElementById('fileInfo');
    const placeholder = document.getElementById('videoPlaceholder');
    const player = document.getElementById('outputVideoPlayer');
    const badge = document.getElementById('playerStatusBadge');
    const videoSource = document.getElementById('videoSource');
    const clearBtn = document.getElementById('clearBtn');
    const overlayClose = document.getElementById('videoOverlayClose');
    const dropZone = document.getElementById('videoDropZone');

    fileInput.value = '';
    if (fileInfo) fileInfo.classList.add('hidden');
    if (clearBtn) clearBtn.classList.add('hidden');
    if (overlayClose) overlayClose.classList.add('hidden');
    if (placeholder) placeholder.classList.remove('hidden');
    if (player) {
        player.pause();
        player.src = '';
        player.classList.add('hidden');
    }
    if (videoSource) videoSource.src = '';
    // Reset drop zone & controls width for placeholder
    if (dropZone) {
        dropZone.style.width = '';
        dropZone.classList.remove('has-video');
    }
    const controls = document.getElementById('playerControls');
    if (controls) {
        controls.style.width = '';
        controls.style.maxWidth = '';
    }
    if (badge) {
        badge.innerHTML = '<i class="fa-solid fa-upload"></i> Drop Video Here';
        badge.className = 'badge badge-info';
    }
    updateUnifiedButtonState('reset');
    clearLiveSubtitle();

    // Lock the Transcript button — no video is loaded
    const processBtn = document.getElementById('unifiedProcessBtn');
    if (processBtn) {
        processBtn.disabled = true;
        processBtn.style.opacity = '0.45';
        processBtn.style.cursor = 'not-allowed';
        processBtn.style.pointerEvents = 'none';
    }

    // Reset dubbed audio track and unmute original player
    if (dubbedAudioTrack) {
        dubbedAudioTrack.pause();
        dubbedAudioTrack.src = '';
        dubbedAudioTrack = null;
    }
    dubbedAudioActive = false;
    if (player) {
        player.muted = false;
        player.volume = 1.0;
    }

    // Also reset transcribed state so button goes back to "Transcribe"
    currentJobData = null;
    currentJobId = null;
    isTranscribed = false;

    // Clear transcript segments list and restore empty placeholder
    const segmentsList = document.getElementById('segmentsList');
    const emptyPlaceholder = document.getElementById('emptyTranscriptPlaceholder');
    if (segmentsList) {
        segmentsList.innerHTML = '';
        segmentsList.classList.add('hidden');
    }
    if (emptyPlaceholder) {
        emptyPlaceholder.classList.remove('hidden');
    }
}

function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return "00:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function updateBgmVolumePreview(val) {
    const valSpan = document.getElementById('valBgmVolume');
    if (valSpan) valSpan.textContent = val + '%';
    const player = document.getElementById('outputVideoPlayer');
    if (player) {
        applyPreviewBgmVolume(player);
    }
}

function applyPreviewBgmVolume(player) {
    if (!player) return;
    const vocalMode = typeof getSelectedVocalMode === 'function' ? getSelectedVocalMode() : 'remove';
    const bgmVolSlider = document.getElementById('bgmVolume');
    const bgmPct = bgmVolSlider ? parseFloat(bgmVolSlider.value) : 100.0;
    const volFactor = Math.min(1.0, Math.max(0, bgmPct / 100.0));

    if (vocalMode === 'mute') {
        player.muted = true;
        player.volume = 0;
    } else if (vocalMode === 'keep' || vocalMode === 'remove') {
        player.muted = false;
        player.volume = volFactor;
    } else if (vocalMode === 'duck') {
        player.muted = false;
        player.volume = 0.35 * volFactor;
    }
}

function initCustomPlayerControls() {
    const player = document.getElementById('outputVideoPlayer');
    const scrubber = document.getElementById('videoScrubber');
    const timeDisplay = document.getElementById('timeDisplay');
    const playIcon = document.getElementById('playIcon');

    if (!player) return;

    player.addEventListener('timeupdate', () => {
        if (player.duration) {
            const pct = (player.currentTime / player.duration) * 100;
            if (scrubber) scrubber.value = pct;
            if (timeDisplay) timeDisplay.textContent = `${formatTime(player.currentTime)} / ${formatTime(player.duration)}`;
        }
        updateLiveSubtitle(player.currentTime);
    });

    player.addEventListener('play', () => {
        if (playIcon) playIcon.className = 'fa-solid fa-pause';
        applyPreviewBgmVolume(player);
        if (dubbedAudioActive && dubbedAudioTrack && dubbedAudioTrack.src) {
            dubbedAudioTrack.currentTime = player.currentTime;
            dubbedAudioTrack.play().catch(e => console.log('Dubbed audio play error:', e));
        }
    });

    player.addEventListener('pause', () => {
        if (playIcon) playIcon.className = 'fa-solid fa-play';
        if (dubbedAudioTrack) dubbedAudioTrack.pause();
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        // Don't restore volume here — keep original muted while dubbed track is loaded
    });

    player.addEventListener('seeking', () => {
        if (dubbedAudioTrack && dubbedAudioTrack.src) {
            dubbedAudioTrack.currentTime = player.currentTime;
        }
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        // Keep original muted while dubbed track is active
    });

    player.addEventListener('ended', () => {
        if (playIcon) playIcon.className = 'fa-solid fa-play';
        if (dubbedAudioTrack) { dubbedAudioTrack.pause(); dubbedAudioTrack.currentTime = 0; }
        if ('speechSynthesis' in window) window.speechSynthesis.cancel();
        clearLiveSubtitle();
    });

    if (scrubber) {
        scrubber.addEventListener('input', () => {
            if (player.duration) {
                player.currentTime = (scrubber.value / 100) * player.duration;
            }
        });
    }
}

function togglePlayPause() {
    const player = document.getElementById('outputVideoPlayer');
    if (!player) return;
    if (player.paused) {
        player.play();
    } else {
        player.pause();
    }
}

function toggleMute() {
    const player = document.getElementById('outputVideoPlayer');
    const muteIcon = document.getElementById('muteIcon');
    if (!player) return;
    player.muted = !player.muted;
    if (muteIcon) {
        muteIcon.className = player.muted ? 'fa-solid fa-volume-xmark' : 'fa-solid fa-volume-high';
    }
}

function toggleFullscreen() {
    const container = document.getElementById('videoDropZone');
    if (!container) return;
    if (!document.fullscreenElement) {
        if (container.requestFullscreen) container.requestFullscreen();
    } else {
        if (document.exitFullscreen) document.exitFullscreen();
    }
}

function getSelectedVocalMode() {
    const radios = document.getElementsByName('vocalMode');
    for (const r of radios) {
        if (r.checked) return r.value;
    }
    return 'remove';
}

// --- Two-Step Workflow & Collapsible Main Studio Tabs ---
function switchMainTab(tabId) {
    const transcriptBtn = document.getElementById('tabBtnTranscript');
    const customizationBtn = document.getElementById('tabBtnCustomization');
    const transcriptPanel = document.getElementById('mainPanelTranscript');
    const customizationPanel = document.getElementById('mainPanelCustomization');
    const content = document.getElementById('mainTabContent');

    if (content) content.classList.remove('collapsed');

    if (tabId === 'transcript') {
        if (transcriptBtn) transcriptBtn.classList.add('active');
        if (customizationBtn) customizationBtn.classList.remove('active');
        if (transcriptPanel) transcriptPanel.classList.add('active');
        if (customizationPanel) customizationPanel.classList.remove('active');
    } else {
        if (customizationBtn) customizationBtn.classList.add('active');
        if (transcriptBtn) transcriptBtn.classList.remove('active');
        if (customizationPanel) customizationPanel.classList.add('active');
        if (transcriptPanel) transcriptPanel.classList.remove('active');
    }

    // Opening/closing the Editor Lab panel can change the video preview box's rendered
    // size, and updateLivePreviewOverlays() measures that real size to scale font/outline
    // percentages — recompute now so the overlays don't lag a stale layout.
    updateLivePreviewOverlays();
}

function toggleMainPanelCollapse() {
    const content = document.getElementById('mainTabContent');
    const chevron = document.getElementById('collapseChevron');
    if (!content) return;

    content.classList.toggle('collapsed');
    if (chevron) {
        chevron.className = content.classList.contains('collapsed')
            ? 'fa-solid fa-chevron-down'
            : 'fa-solid fa-chevron-up';
    }
}

function getRvcModelParams() {
    const toggle = document.getElementById('rvcToggle');

    // Toggle is the definitive on/off switch.
    // If RVC is disabled, always return 'none' → EdgeTTS output used as-is.
    if (!toggle || !toggle.checked) {
        return { rvcModel: 'none', rvcPitch: '0' };
    }

    const select = document.getElementById('rvcModelSelect');
    const val    = select ? select.value : 'none';
    const pitch  = document.getElementById('rvcPitch')?.value || '0';
    return { rvcModel: val, rvcPitch: pitch };
}

function onRvcModelSelectChange(select) {
    if (typeof onRvcToggleChange === 'function') onRvcToggleChange();

    const previewBtn = document.getElementById('btnPreviewRvcVoice');
    if (previewBtn) {
        const isAuto = select && select.value === 'auto_gender_match';
        previewBtn.disabled = isAuto;
        previewBtn.title = isAuto
            ? 'Auto Gender Match uses a different voice per segment — preview each tagged model individually in Voice Config instead.'
            : '';
    }
}

async function startTranscriptionOnly() {
    const fileInput = document.getElementById('videoFileInput');
    const fileToUpload = (fileInput && fileInput.files && fileInput.files.length > 0) ? fileInput.files[0] : loadedVideoFile;

    if (!fileToUpload) {
        alert('Please select or drop a video file first!');
        return;
    }

    const targetLangSelect = document.getElementById('targetLangSelect');
    const whisperModelSelect = document.getElementById('whisperModelSelect');

    const targetLang = targetLangSelect ? targetLangSelect.value : 'km';
    const whisperModel = whisperModelSelect ? whisperModelSelect.value : 'base';

    const voiceSelect = document.getElementById('voiceSelect');
    const voiceId = voiceSelect ? voiceSelect.value : 'auto';

    const recapStyleSelect = document.getElementById('recapStyleSelect');
    const recapStyle = recapStyleSelect ? recapStyleSelect.value : 'dramatic';
    const isRecap = (currentWorkflowMode === 'recap');

    showProgressSection(isRecap ? '🎬 Generating AI Movie Recap...' : '🎙️ Transcribing Audio...', 'transcribe');

    const geminiKeyEl = document.getElementById('geminiApiKeyInput');
    const geminiApiKey = geminiKeyEl ? geminiKeyEl.value.trim() : '';
    const geminiModelSelect = document.getElementById('geminiModelSelect');
    const geminiModel = geminiModelSelect ? geminiModelSelect.value : 'gemini-2.0-flash';

    const { rvcModel, rvcPitch } = getRvcModelParams();




    const vocalMode = getSelectedVocalMode();
    const formData = new FormData();
    formData.append('video_file', fileToUpload);
    formData.append('target_lang', targetLang);
    formData.append('whisper_model', whisperModel);
    formData.append('voice_id', voiceId);
    formData.append('vocal_mode', vocalMode);
    formData.append('is_recap', isRecap ? 'true' : 'false');
    formData.append('recap_style', recapStyle);
    formData.append('rvc_model', rvcModel);
    formData.append('rvc_pitch', rvcPitch);

    const savedFolder = localStorage.getItem('userCustomSaveFolder') || '';
    if (savedFolder) {
        formData.append('output_path', savedFolder);
    }

    if (geminiApiKey) {
        formData.append('gemini_api_key', geminiApiKey);
        formData.append('gemini_model', geminiModel);
    }


    const groqKeyInput = document.getElementById('groqApiKeyInput');
    const groqApiKey = groqKeyInput ? groqKeyInput.value.trim() : (localStorage.getItem('groq_api_key') || '');
    if (groqApiKey) {
        formData.append('groq_api_key', groqApiKey);
    }

    const openrouterKeyInput = document.getElementById('openrouterApiKeyInput');
    const openrouterApiKey = openrouterKeyInput ? openrouterKeyInput.value.trim() : (localStorage.getItem('openrouter_api_key') || '');
    if (openrouterApiKey) {
        formData.append('openrouter_api_key', openrouterApiKey);
    }

    const openaiKeyInput = document.getElementById('openaiApiKeyInput');
    const openaiApiKey = openaiKeyInput ? openaiKeyInput.value.trim() : (localStorage.getItem('openai_api_key') || '');
    if (openaiApiKey) {
        formData.append('openai_api_key', openaiApiKey);
    }

    const deepseekKeyInput = document.getElementById('deepseekApiKeyInput');
    const deepseekApiKey = deepseekKeyInput ? deepseekKeyInput.value.trim() : (localStorage.getItem('deepseek_api_key') || '');
    if (deepseekApiKey) {
        formData.append('deepseek_api_key', deepseekApiKey);
    }

    // Primary AI model for context analyzer & translation cascade
    const primaryAiModel = localStorage.getItem('primary_ai_model') || 'gemini';
    formData.append('primary_ai_model', primaryAiModel);

    const introCheck = document.getElementById('introSpeechCheck');
    const introInput = document.getElementById('introSpeechInput');
    const outroCheck = document.getElementById('outroSpeechCheck');
    const outroInput = document.getElementById('outroSpeechInput');
    if (introCheck && introCheck.checked && introInput && introInput.value.trim()) {
        formData.append('intro_speech', introInput.value.trim());
    }
    if (outroCheck && outroCheck.checked && outroInput && outroInput.value.trim()) {
        formData.append('outro_speech', outroInput.value.trim());
    }

    try {
        const response = await fetch('/api/transcribe_only', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.job_id) {
            currentJobId = data.job_id;
            listenToTranscribeProgress(data.job_id);
        } else {
            alert('Error: ' + (data.error || 'Failed to start transcription'));
            hideProgressSection();
        }
    } catch (err) {
        alert('Failed to start transcription: ' + err.message);
        hideProgressSection();
    }
}

let isTranscribed = false;

function updateUnifiedButtonState(state) {
    const btn = document.getElementById('unifiedProcessBtn');
    if (!btn) return;

    if (state === 'transcribed' || state === 'completed') {
        isTranscribed = true;
        btn.className = 'btn btn-primary btn-large btn-glow btn-block margin-top-xs';
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Final Process';
    } else {
        isTranscribed = false;
        btn.className = 'btn btn-primary btn-large btn-glow btn-block margin-top-xs';
        if (currentWorkflowMode === 'recap') {
            btn.innerHTML = '<i class="fa-solid fa-clapperboard"></i> Generate AI Movie Recap';
        } else {
            btn.innerHTML = '<i class="fa-solid fa-microphone"></i> Transcript';
        }
    }
}

function handleUnifiedProcessClick() {
    if (isTranscribed) {
        startFinalProcess();
    } else {
        startTranscriptionOnly();
    }
}

function listenToTranscribeProgress(jobId) {
    if (eventSource) eventSource.close();

    eventSource = new EventSource(`/api/progress/${jobId}`);

    eventSource.onmessage = (event) => {
        const evtData = JSON.parse(event.data);
        updateProgressUI(evtData);

        if (evtData.status === 'transcribed' || evtData.status === 'completed') {
            eventSource.close();
            currentJobData = evtData.result_data;

            // Mark all 4 transcription steps as completed before closing
            ['extract_audio', 'transcribe', 'translate', 'tts_synthesis'].forEach(stepKey => {
                const el = document.getElementById(`step_${stepKey}`);
                if (el) { el.classList.add('completed'); el.classList.remove('active'); }
            });

            // Short pause so user sees all steps complete
            setTimeout(() => {
                hideProgressSection();
                updateUnifiedButtonState('transcribed');

                if (evtData.result_data) {
                    if (evtData.result_data.segments) {
                        renderTranscriptSegments(evtData.result_data.segments);
                        enableLiveSubtitles();
                    }
                    if (evtData.result_data.dubbed_audio_url) {
                        loadDubbedAudioTrack(evtData.result_data.dubbed_audio_url);
                    }
                }
                switchMainTab('transcript');
            }, 700);
        } else if (evtData.status === 'failed') {
            eventSource.close();
            alert('Transcription failed: ' + (evtData.error || evtData.message));
            hideProgressSection();
        }
    };
}

let currentDubbedAudioElement = null;

function loadDubbedAudioTrack(audioUrl) {

    const player = document.getElementById('outputVideoPlayer');
    if (!player) return;

    if (currentDubbedAudioElement) {
        try { currentDubbedAudioElement.pause(); } catch(e) {}
        currentDubbedAudioElement = null;
    }

    const audio = new Audio(audioUrl + '?t=' + Date.now());
    currentDubbedAudioElement = audio;

    applyPreviewBgmVolume(player);

    player.onplay = () => {
        if (currentDubbedAudioElement) {
            currentDubbedAudioElement.currentTime = player.currentTime;
            currentDubbedAudioElement.play().catch(e => console.warn('Dubbed audio play:', e));
        }
    };

    player.onpause = () => {
        if (currentDubbedAudioElement) {
            currentDubbedAudioElement.pause();
        }
    };

    player.onseeking = () => {
        if (currentDubbedAudioElement) {
            currentDubbedAudioElement.currentTime = player.currentTime;
        }
    };

    player.onratechange = () => {
        if (currentDubbedAudioElement) {
            currentDubbedAudioElement.playbackRate = player.playbackRate;
        }
    };

    if (!player.paused) {
        audio.currentTime = player.currentTime;
        audio.play().catch(e => console.warn('Dubbed audio play:', e));
    }
}


function renderTranscriptSegments(segments) {
    const container = document.getElementById('segmentsList');
    const placeholder = document.getElementById('emptyTranscriptPlaceholder');
    const countSpan = document.getElementById('transcriptSegCount');

    if (placeholder) placeholder.classList.add('hidden');
    if (container) container.classList.remove('hidden');

    if (countSpan && Array.isArray(segments)) {
        countSpan.textContent = `${segments.length} segments transcribed`;
    }

    renderTranscriptCards(segments);
}

// ─── Live Subtitle Engine ──────────────────────────────────────
let liveSubEnabled = false;
let lastSubIdx = -1;

function enableLiveSubtitles() {
    const subToggle = document.getElementById('subToggle');
    if (subToggle && subToggle.checked) {
        liveSubEnabled = true;
        const overlay = document.getElementById('liveSubOverlay');
        if (overlay) overlay.classList.remove('hidden');
    } else {
        clearLiveSubtitle();
    }
}

let dubbedAudioTrack = null;
let dubbedAudioActive = false;  // flag: real dubbed audio is loaded and should be the only source

function loadDubbedAudioTrack(url) {
    if (!dubbedAudioTrack) {
        dubbedAudioTrack = document.createElement('audio');
        dubbedAudioTrack.id = 'dubbedAudioTrack';
        document.body.appendChild(dubbedAudioTrack);
    }
    dubbedAudioTrack.src = url;
    dubbedAudioTrack.load();
    dubbedAudioActive = true;

    // Synchronize video player audio volume based on active Vocal Treatment setting
    applyPreviewBgmVolume(player);
}

function clearLiveSubtitle() {
    liveSubEnabled = false;
    lastSubIdx = -1;
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    const overlay = document.getElementById('liveSubOverlay');
    const overlayImg = document.getElementById('liveSubOverlayImg');
    if (overlayImg) overlayImg.src = '';
    if (overlay) {
        overlay.classList.add('hidden');
        overlay.classList.remove('sub-visible');
    }
    document.querySelectorAll('.segment-row.active-segment').forEach(r => r.classList.remove('active-segment'));
}

function speakRealtimeSegmentSpeech(text) {
    if (!('speechSynthesis' in window) || !text) return;
    try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        const targetLang = document.getElementById('targetLangSelect') ? document.getElementById('targetLangSelect').value : 'km';
        utterance.lang = targetLang;
        utterance.rate = 1.0;

        const player = document.getElementById('outputVideoPlayer');
        if (player) {
            if (player._savedVolume === undefined) player._savedVolume = player.volume;
            // Duck original video volume to 10% so target dubber speech is loud and clear
            player.volume = 0.1;
            utterance.onend = () => {
                if (player && player._savedVolume !== undefined) player.volume = player._savedVolume;
            };
            utterance.onerror = () => {
                if (player && player._savedVolume !== undefined) player.volume = player._savedVolume;
            };
        }

        window.speechSynthesis.speak(utterance);
    } catch (e) {
        console.warn('Realtime TTS error:', e);
    }
}

function wrapTextForPreview(text, maxChars = 20) {
    if (!text) return '';
    if (text.length <= maxChars || text.includes('\n')) return text;

    const pattern = /[\u1780-\u17b3](?:[\u17d2][\u1780-\u17b3])?[\u17b6-\u17c5]*[\u17c6-\u17d3]*|[^\u1780-\u17d3\s]+|\s+/g;
    const syllables = text.match(pattern) || [];

    let lines = [];
    let currLine = '';
    syllables.forEach(s => {
        if ((currLine + s).length > maxChars && currLine.trim()) {
            lines.push(currLine.trim());
            currLine = s;
        } else {
            currLine += s;
        }
    });
    if (currLine.trim()) {
        lines.push(currLine.trim());
    }
    return lines.join('\n');
}

let lastPreviewCacheKey = '';
const subtitlePreviewCache = new Map();

function clearSubtitlePreviewCache() {
    subtitlePreviewCache.clear();
    lastPreviewCacheKey = '';
}

async function fetchPythonLivePreviewOverlay(text) {
    const subToggle = document.getElementById('subToggle');
    const overlay = document.getElementById('liveSubOverlay');
    if (!overlay) return;

    let overlayImg = document.getElementById('liveSubOverlayImg');
    if (!overlayImg) {
        overlayImg = document.createElement('img');
        overlayImg.id = 'liveSubOverlayImg';
        overlayImg.style.width = '100%';
        overlayImg.style.height = '100%';
        overlayImg.style.objectFit = 'contain';
        overlayImg.style.pointerEvents = 'none';
        overlayImg.style.display = 'block';
        overlay.appendChild(overlayImg);
    }
    
    if (subToggle && !subToggle.checked) {
        overlay.classList.add('hidden');
        return;
    }

    if (!text || !text.trim()) {
        text = 'Sample Subtitle Text';
    }

    const subConfig = collectCustomizationSettings().subtitles;
    const player = document.getElementById('outputVideoPlayer');
    const vw = player && player.videoWidth && player.videoWidth > 0 ? player.videoWidth : 1080;
    const vh = player && player.videoHeight && player.videoHeight > 0 ? player.videoHeight : 1920;

    const cacheKey = JSON.stringify({ text, subConfig, vw, vh });
    if (cacheKey === lastPreviewCacheKey && overlayImg.src) {
        overlay.classList.remove('hidden');
        overlay.style.display = 'block';
        overlay.style.opacity = '1';
        return;
    }

    // Fast 0ms memory cache hit for smooth playback & scrubbing
    if (subtitlePreviewCache.has(cacheKey)) {
        const cachedImgUrl = subtitlePreviewCache.get(cacheKey);
        overlayImg.src = cachedImgUrl;
        overlay.classList.remove('hidden');
        overlay.style.display = 'block';
        overlay.style.opacity = '1';
        lastPreviewCacheKey = cacheKey;
        return;
    }

    try {
        const res = await fetch('/api/preview_overlay', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, sub_cfg: subConfig, width: vw, height: vh })
        });
        if (res.ok) {
            const data = await res.json();
            if (data && data.ok && data.image) {
                // Double-buffered preloading for flicker-free image transitions
                const tempImg = new Image();
                tempImg.onload = () => {
                    overlayImg.src = tempImg.src;
                    overlay.classList.remove('hidden');
                    overlay.style.display = 'block';
                    overlay.style.opacity = '1';

                    overlay.classList.remove('anim-pop', 'anim-fade', 'anim-slide');
                    const anim = subConfig ? subConfig.anim : 'None';
                    if (anim === 'Pop') {
                        void overlay.offsetWidth;
                        overlay.classList.add('anim-pop');
                    } else if (anim === 'Fade') {
                        void overlay.offsetWidth;
                        overlay.classList.add('anim-fade');
                    } else if (anim === 'Slide') {
                        void overlay.offsetWidth;
                        overlay.classList.add('anim-slide');
                    }

                    if (subtitlePreviewCache.size > 60) {
                        const firstKey = subtitlePreviewCache.keys().next().value;
                        subtitlePreviewCache.delete(firstKey);
                    }
                    subtitlePreviewCache.set(cacheKey, data.image);
                    lastPreviewCacheKey = cacheKey;
                };
                tempImg.src = data.image;
            }
        }
    } catch (e) {
        console.warn('Preview overlay fetch error:', e);
    }
}

function updateLiveSubtitle(currentTime) {
    const subToggle = document.getElementById('subToggle');
    if (!subToggle || !subToggle.checked) {
        clearLiveSubtitle();
        return;
    }

    if (!currentJobData || !currentJobData.segments || currentJobData.segments.length === 0) {
        // Fallback for initial launch demo preview before video is transcribed
        fetchPythonLivePreviewOverlay('Sample Subtitle Text');
        return;
    }

    const segs = currentJobData.segments;
    let found = -1;

    for (let i = 0; i < segs.length; i++) {
        if (currentTime >= segs[i].start && currentTime <= segs[i].end) {
            found = i;
            break;
        }
    }

    const player = document.getElementById('outputVideoPlayer');
    const isPaused = !player || player.paused;

    if (found >= 0) {
        lastSubIdx = found;
        const segId = segs[found].id || (found + 1);
        const input = document.getElementById(`trans_input_${segId}`) || document.getElementById(`segInput_${found}`) || document.getElementById(`trans_input_${found}`);
        const text = input ? input.value : (segs[found].translated_text || segs[found].text || '');
        
        fetchPythonLivePreviewOverlay(text);

        document.querySelectorAll('.segment-card.active-segment, .segment-row.active-segment').forEach(r => r.classList.remove('active-segment'));
        const card = document.getElementById(`seg_card_${segId}`) || document.getElementById(`segRow_${found}`);
        if (card) {
            card.classList.add('active-segment');
            card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    } else if (isPaused) {
        const activeIdx = Math.max(0, lastSubIdx >= 0 ? lastSubIdx : 0);
        const segId = segs[activeIdx].id || (activeIdx + 1);
        const input = document.getElementById(`trans_input_${segId}`) || document.getElementById(`segInput_${activeIdx}`) || document.getElementById(`trans_input_${activeIdx}`);
        const text = input ? input.value : (segs[activeIdx].translated_text || segs[activeIdx].text || 'Sample Subtitle Text');
        fetchPythonLivePreviewOverlay(text);
    } else {
        const overlay = document.getElementById('liveSubOverlay');
        if (overlay) overlay.classList.add('hidden');
    }
}

function collectEditedSegments() {
    if (!currentJobData || !currentJobData.segments) return [];

    const inputs = document.querySelectorAll('.segment-input-line');
    const edited = [...currentJobData.segments];

    inputs.forEach((input, idx) => {
        if (edited[idx]) {
            edited[idx].translated_text = input.value;
            // Persist per-segment gender override
            const genderBtn = document.getElementById(`segGender_${idx}`);
            if (genderBtn) {
                edited[idx].gender = genderBtn.dataset.gender || 'auto';
            }
        }
    });

    return edited;
}

function collectCustomizationSettings() {
    const getVal = (id, def) => {
        const el = document.getElementById(id);
        return el ? el.value : def;
    };
    const getNum = (id, def) => {
        const el = document.getElementById(id);
        return el ? parseFloat(el.value) : def;
    };
    const getBool = (id, def) => {
        const el = document.getElementById(id);
        return el ? el.checked : def;
    };

    return {
        audio: {
            bgm_volume: getNum('bgmVolume', 100)
        },
        mirror: {
            enabled: getBool('mirrorToggle', false)
        },
        color: {
            enabled: getBool('colorToggle', false),
            brightness: getNum('colorBrightness', 0),
            contrast: getNum('colorContrast', 100),
            saturation: getNum('colorSaturation', 100),
            hue: getNum('colorHue', 0)
        },
        blur: {
            enabled: getBool('blurToggle', false),
            auto_detect: getBool('blurAutoDetectToggle', false),
            posY: getNum('blurPosY', 57.3),
            height: getNum('blurHeight', 7),
            posX: getNum('blurPosX', 0),
            width: getNum('blurWidth', 100),
            opacity: getNum('blurOpacity', 100)
        },

        subtitles: (() => {
            const f = getSelectedFont('subFont');
            const isBold = document.getElementById('subBoldBtn')?.classList.contains('active') || false;
            const isItalic = document.getElementById('subItalicBtn')?.classList.contains('active') || false;
            return {
                enabled: getBool('subToggle', false),
                preset: getVal('subStylePreset', 'Outline'),
                font: f.name,
                font_path: f.path,
                size: getNum('subSize', 3),
                opacity: getNum('subTextOpacity', 100),
                outline: getNum('subOutline', 0.3),
                posY: getNum('subPos', 62),
                anim: getVal('subAnim', 'None'),
                max_chars: getNum('subMaxChars', 36),
                text_color: getVal('subTextColor', '#FFFFFF'),
                outline_color: getVal('subOutlineColor', '#000000'),
                bold: isBold,
                italic: isItalic
            };
        })(),
        text: (() => {
            const f = getSelectedFont('textFont');
            const getBool = (id, def) => { const el = document.getElementById(id); return el ? el.checked : def; };
            const getVal = (id, def) => { const el = document.getElementById(id); return el ? el.value : def; };
            const getNum = (id, def) => { const el = document.getElementById(id); return el ? parseFloat(el.value) : def; };
            const isBold = document.getElementById('textBoldBtn')?.classList.contains('active') || false;
            const isItalic = document.getElementById('textItalicBtn')?.classList.contains('active') || false;

            return {
                enabled: getBool('textToggle', false),
                content: getVal('overlayText', ''),
                font: f.name,
                font_path: f.path,
                anim: getVal('textAnim', 'slide_top'),
                speed: getNum('textSpeed', 10),
                size: getNum('textSize', 3),
                opacity: getNum('textOpacity', 90),
                bg_opacity: getNum('textBgOpacity', 0),
                outline: getNum('textOutlineWidth', 0),
                shadow: getNum('textShadow', 0),
                posY: getNum('textPosY', 15),
                color_fill: getVal('textColorFill', '#FFFFFF'),
                color_bg: getVal('textColorBg', '#808080'),
                color_outline: getVal('textColorOutline', '#FFFFFF'),
                bold: isBold,
                italic: isItalic,
                loop: getBool('textLoopToggle', true)
            };
        })(),
        logo: {
            enabled: getBool('logoToggle', false),
            size: getNum('logoSize', 54),
            opacity: getNum('logoOpacity', 10),
            radius: getNum('logoRadius', 0)
        }
    };
}

// ─── Global Editing Preset Management ───────────────────────────────────────
const DEFAULT_GLOBAL_PRESETS = [
    {
        id: 'preset_default_clean',
        name: '✨ Default Clean (No Overlay)',
        isBuiltin: true,
        settings: {
            audio: { bgm_volume: 100 },
            mirror: { enabled: false },
            color: { enabled: false, brightness: 0, contrast: 100, saturation: 100, hue: 0 },
            blur: { enabled: false, posY: 57.3, height: 7, posX: 0, width: 100, opacity: 100 },
            subtitles: { enabled: false, preset: 'Outline', font: 'Arial', size: 3, opacity: 100, outline: 0.3, posY: 62, anim: 'None', max_chars: 0, text_color: '#FFFFFF', outline_color: '#000000', bold: false, italic: false },
            text: { enabled: false, content: '', font: 'Arial', anim: 'slide_top', speed: 10, size: 3, opacity: 90, bg_opacity: 0, outline: 0, shadow: 0, posY: 15, color_fill: '#FFFFFF', color_bg: '#808080', color_outline: '#FFFFFF', bold: false, italic: false, loop: true },
            logo: { enabled: false, size: 54, opacity: 10, radius: 0 }
        }
    },
    {
        id: 'preset_cinematic_subtitles',
        name: '🎬 Cinematic Subtitles (Yellow & Black Outline)',
        isBuiltin: true,
        settings: {
            audio: { bgm_volume: 100 },
            mirror: { enabled: false },
            color: { enabled: true, brightness: 5, contrast: 108, saturation: 110, hue: 0 },
            blur: { enabled: false, posY: 57.3, height: 7, posX: 0, width: 100, opacity: 100 },
            subtitles: { enabled: true, preset: 'Outline', font: 'Arial', size: 3.2, opacity: 100, outline: 0.5, posY: 85, anim: 'None', max_chars: 0, text_color: '#FFEA00', outline_color: '#000000', bold: true, italic: false },
            text: { enabled: false, content: '', font: 'Arial', anim: 'slide_top', speed: 10, size: 3, opacity: 90, bg_opacity: 0, outline: 0, shadow: 0, posY: 15, color_fill: '#FFFFFF', color_bg: '#808080', color_outline: '#FFFFFF', bold: false, italic: false, loop: true },
            logo: { enabled: false, size: 54, opacity: 10, radius: 0 }
        }
    },
    {
        id: 'preset_shorts_recap',
        name: '📱 YouTube Shorts / TikTok Recap (Blur + Subtitles)',
        isBuiltin: true,
        settings: {
            audio: { bgm_volume: 85 },
            mirror: { enabled: false },
            color: { enabled: true, brightness: 8, contrast: 115, saturation: 120, hue: 0 },
            blur: { enabled: true, posY: 70, height: 12, posX: 0, width: 100, opacity: 90 },
            subtitles: { enabled: true, preset: 'Highlight', font: 'Arial', size: 3.5, opacity: 100, outline: 0.6, posY: 72, anim: 'pop_in', max_chars: 0, text_color: '#FFFFFF', outline_color: '#000000', bold: true, italic: false },

            text: { enabled: true, content: 'FOLLOW FOR MORE', font: 'Arial', anim: 'fade', speed: 10, size: 2.5, opacity: 90, bg_opacity: 50, outline: 0.2, shadow: 1, posY: 10, color_fill: '#FF0050', color_bg: '#000000', color_outline: '#FFFFFF', bold: true, italic: false, loop: true },
            logo: { enabled: false, size: 54, opacity: 10, radius: 0 }
        }
    }
];

function getGlobalPresets() {
    try {
        const raw = localStorage.getItem('global_editing_presets');
        if (raw) {
            const list = JSON.parse(raw);
            if (Array.isArray(list) && list.length > 0) return list;
        }
    } catch (e) {}
    localStorage.setItem('global_editing_presets', JSON.stringify(DEFAULT_GLOBAL_PRESETS));
    return DEFAULT_GLOBAL_PRESETS;
}

function saveGlobalPresetsList(list) {
    localStorage.setItem('global_editing_presets', JSON.stringify(list));
}

function initBatchPresetDropdown() {
    const sel = document.getElementById('batchPresetSelect');
    if (!sel) return;

    const list = getGlobalPresets();
    const activeBatchPresetId = localStorage.getItem('active_batch_preset_id') || '__none__';

    let html = `<option value="__none__" ${activeBatchPresetId === '__none__' ? 'selected' : ''}>— No Preset —</option>`;
    html += list.map(p => `
        <option value="${p.id}" ${p.id === activeBatchPresetId ? 'selected' : ''}>
            ${p.name}
        </option>
    `).join('');

    sel.innerHTML = html;
}

function applyBatchPresetChange(presetId) {
    if (isBatchRunning) {
        if (typeof showToast === 'function') {
            showToast('⚠️ Cannot change Editing Preset while batch processing is running!', 'warning');
        }
        // Revert select back to saved active batch preset
        const sel = document.getElementById('batchPresetSelect');
        if (sel) {
            sel.value = localStorage.getItem('active_batch_preset_id') || '__none__';
        }
        return;
    }
    localStorage.setItem('active_batch_preset_id', presetId || '__none__');
    if (presetId && presetId !== '__none__') {
        const list = getGlobalPresets();
        const preset = list.find(p => p.id === presetId);
        if (preset && typeof showToast === 'function') {
            showToast(`🔖 Selected preset "${preset.name}" for Batch Processing`, 'info');
        }
    }
}


function initGlobalPresetDropdown() {
    const sel = document.getElementById('globalPresetSelect');
    if (sel) {
        const list = getGlobalPresets();
        const activeId = localStorage.getItem('active_global_preset_id') || list[0].id;

        sel.innerHTML = list.map(p => `
            <option value="${p.id}" ${p.id === activeId ? 'selected' : ''}>
                ${p.name}
            </option>
        `).join('');
    }
    initBatchPresetDropdown();
}


function applyCustomizationSettings(s) {
    if (!s) return;

    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined) el.value = val;
    };
    const setBool = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined) el.checked = !!val;
    };
    const setNum = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined) {
            el.value = val;
            const valSpan = document.getElementById(id + 'Val');
            if (valSpan) valSpan.textContent = val;
        }
    };

    // 1. Audio
    if (s.audio) {
        setNum('bgmVolume', s.audio.bgm_volume);
    }
    // 2. Mirror
    if (s.mirror) {
        setBool('mirrorToggle', s.mirror.enabled);
    }
    // 3. Color
    if (s.color) {
        setBool('colorToggle', s.color.enabled);
        setNum('colorBrightness', s.color.brightness);
        setNum('colorContrast', s.color.contrast);
        setNum('colorSaturation', s.color.saturation);
        setNum('colorHue', s.color.hue);
    }
    // 4. Blur
    if (s.blur) {
        setBool('blurToggle', s.blur.enabled);
        setBool('blurAutoDetectToggle', s.blur.auto_detect);
        setNum('blurPosY', s.blur.posY);
        setNum('blurHeight', s.blur.height);
        setNum('blurPosX', s.blur.posX);
        setNum('blurWidth', s.blur.width);
        setNum('blurOpacity', s.blur.opacity);
    }

    // 5. Subtitles
    if (s.subtitles) {
        setBool('subToggle', s.subtitles.enabled);
        setVal('subStylePreset', s.subtitles.preset || 'Outline');
        if (s.subtitles.font) setVal('subFont', s.subtitles.font);
        setNum('subSize', s.subtitles.size);
        setNum('subTextOpacity', s.subtitles.opacity);
        setNum('subOutline', s.subtitles.outline);
        setNum('subPos', s.subtitles.posY);
        setVal('subAnim', s.subtitles.anim || 'None');
        setNum('subMaxChars', s.subtitles.max_chars);
        setVal('subTextColor', s.subtitles.text_color || '#FFFFFF');
        setVal('subOutlineColor', s.subtitles.outline_color || '#000000');

        const boldBtn = document.getElementById('subBoldBtn');
        if (boldBtn) {
            if (s.subtitles.bold) boldBtn.classList.add('active');
            else boldBtn.classList.remove('active');
        }
        const italicBtn = document.getElementById('subItalicBtn');
        if (italicBtn) {
            if (s.subtitles.italic) italicBtn.classList.add('active');
            else italicBtn.classList.remove('active');
        }
    }
    // 6. Text Overlay
    if (s.text) {
        setBool('textToggle', s.text.enabled);
        setVal('overlayText', s.text.content || '');
        if (s.text.font) setVal('textFont', s.text.font);
        setVal('textAnim', s.text.anim || 'slide_top');
        setNum('textSpeed', s.text.speed);
        setNum('textSize', s.text.size);
        setNum('textOpacity', s.text.opacity);
        setNum('textBgOpacity', s.text.bg_opacity);
        setNum('textOutlineWidth', s.text.outline);
        setNum('textShadow', s.text.shadow);
        setNum('textPosY', s.text.posY);
        setVal('textColorFill', s.text.color_fill || '#FFFFFF');
        setVal('textColorBg', s.text.color_bg || '#808080');
        setVal('textColorOutline', s.text.color_outline || '#FFFFFF');
        setBool('textLoopToggle', s.text.loop !== false);

        const boldBtn = document.getElementById('textBoldBtn');
        if (boldBtn) {
            if (s.text.bold) boldBtn.classList.add('active');
            else boldBtn.classList.remove('active');
        }
        const italicBtn = document.getElementById('textItalicBtn');
        if (italicBtn) {
            if (s.text.italic) italicBtn.classList.add('active');
            else italicBtn.classList.remove('active');
        }
    }
    // 7. Logo Overlay
    if (s.logo) {
        setBool('logoToggle', s.logo.enabled);
        setNum('logoSize', s.logo.size);
        setNum('logoOpacity', s.logo.opacity);
        setNum('logoRadius', s.logo.radius);
    }

    if (typeof updateLivePreviewOverlays === 'function') {
        updateLivePreviewOverlays();
    }
}

function applyGlobalPreset(presetId) {
    if (!presetId) return;
    const list = getGlobalPresets();
    const preset = list.find(p => p.id === presetId);
    if (!preset) return;

    localStorage.setItem('active_global_preset_id', presetId);
    applyCustomizationSettings(preset.settings);
    if (typeof showToast === 'function') {
        showToast(`📁 Applied preset: ${preset.name}`, 'info');
    }
}

async function saveCurrentEditingPreset() {
    const name = await showCustomPrompt('Save New Editing Preset', 'Custom Preset', 'Enter preset name...');
    if (!name || !name.trim()) return;

    const cleanName = name.trim();
    const currentSettings = collectCustomizationSettings();
    const list = getGlobalPresets();

    const newPreset = {
        id: 'preset_' + Date.now(),
        name: '📌 ' + cleanName,
        isBuiltin: false,
        settings: currentSettings
    };

    list.push(newPreset);
    saveGlobalPresetsList(list);
    localStorage.setItem('active_global_preset_id', newPreset.id);
    initGlobalPresetDropdown();

    if (typeof showToast === 'function') {
        showToast(`💾 Saved new preset: "${cleanName}"`, 'success');
    }
}

async function renameGlobalPreset() {
    const sel = document.getElementById('globalPresetSelect');
    if (!sel || !sel.value) return;

    const list = getGlobalPresets();
    const preset = list.find(p => p.id === sel.value);
    if (!preset) return;

    const currentCleanName = preset.name.replace(/^[\s📌✨🎬📱]+/u, '').trim();
    const newName = await showCustomPrompt('Rename Editing Preset', currentCleanName, 'Enter new preset name...');
    if (!newName || !newName.trim()) return;

    const cleanName = newName.trim();
    preset.name = (preset.isBuiltin ? '✨ ' : '📌 ') + cleanName;
    saveGlobalPresetsList(list);
    initGlobalPresetDropdown();

    if (typeof showToast === 'function') {
        showToast(`✏️ Renamed preset to: "${cleanName}"`, 'success');
    }
}

function updateGlobalPreset() {
    const sel = document.getElementById('globalPresetSelect');
    if (!sel || !sel.value) return;

    const list = getGlobalPresets();
    const preset = list.find(p => p.id === sel.value);
    if (!preset) return;

    preset.settings = collectCustomizationSettings();
    saveGlobalPresetsList(list);

    if (typeof showToast === 'function') {
        showToast(`🔄 Updated preset: "${preset.name}" with current editing settings!`, 'success');
    }
}

async function deleteGlobalPreset() {
    const sel = document.getElementById('globalPresetSelect');
    if (!sel || !sel.value) return;

    const list = getGlobalPresets();
    const preset = list.find(p => p.id === sel.value);
    if (!preset) return;

    if (preset.isBuiltin) {
        if (typeof showToast === 'function') {
            showToast('⚠️ Built-in default presets cannot be deleted.', 'warning');
        }
        return;
    }

    const confirmed = await showCustomConfirm(
        'Delete Editing Preset?',
        `Are you sure you want to delete preset "${preset.name}"? This action cannot be undone.`,
        { confirmText: 'Delete Preset', cancelText: 'Cancel', isDanger: true }
    );
    if (!confirmed) return;

    const newList = list.filter(p => p.id !== preset.id);
    saveGlobalPresetsList(newList);
    localStorage.setItem('active_global_preset_id', newList[0].id);
    initGlobalPresetDropdown();
    applyGlobalPreset(newList[0].id);

    if (typeof showToast === 'function') {
        showToast(`🗑️ Preset deleted successfully!`, 'info');
    }
}

// Auto-initialize global preset dropdown on DOM load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        initGlobalPresetDropdown();
        if (typeof silentCheckForUpdates === 'function') {
            setTimeout(silentCheckForUpdates, 3000);
        }
    });
} else {
    setTimeout(() => {
        initGlobalPresetDropdown();
        if (typeof silentCheckForUpdates === 'function') {
            silentCheckForUpdates();
        }
    }, 100);
}



function _setTestBtnState(btnId, state, message) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    const states = {
        idle:    { html: '<i class="fa-solid fa-plug-circle-check"></i> Test', style: '', disabled: false },
        loading: { html: '<i class="fa-solid fa-spinner fa-spin"></i> Testing...', style: 'opacity:0.75;', disabled: true },
        ok:      { html: `<i class="fa-solid fa-circle-check"></i> ${message || 'Connected!'}`, style: 'background:rgba(34,197,94,0.25);border-color:#22c55e;color:#22c55e;', disabled: false },
        fail:    { html: `<i class="fa-solid fa-circle-xmark"></i> ${message || 'Failed'}`, style: 'background:rgba(239,68,68,0.2);border-color:#ef4444;color:#ef4444;', disabled: false },
        warn:    { html: `<i class="fa-solid fa-triangle-exclamation"></i> ${message || 'No Key'}`, style: 'background:rgba(234,179,8,0.2);border-color:#eab308;color:#eab308;', disabled: false },
    };
    const s = states[state] || states.idle;
    btn.innerHTML = s.html;
    btn.style.cssText = `height:32px;padding:0 10px;flex-shrink:0;min-width:72px;transition:all 0.2s;${s.style}`;
    btn.disabled = s.disabled;
    if (state === 'ok' || state === 'fail') {
        setTimeout(() => _setTestBtnState(btnId, 'idle'), 4000);
    }
}

async function testGeminiKeyLive() {
    const keyInput = document.getElementById('geminiApiKeyInput');
    const modelSelect = document.getElementById('geminiModelSelect');
    const key = keyInput ? keyInput.value.trim() : '';
    const model = modelSelect ? modelSelect.value : 'gemini-2.0-flash';

    if (!key) { _setTestBtnState('btnTestGemini', 'warn', 'No Key'); return; }
    _setTestBtnState('btnTestGemini', 'loading');

    try {
        const formData = new FormData();
        formData.append('api_key', key);
        formData.append('model_name', model);
        const res = await fetch('/api/test_gemini_key', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.valid) {
            _setTestBtnState('btnTestGemini', 'ok', 'Connected!');
        } else {
            _setTestBtnState('btnTestGemini', 'fail', 'Invalid Key');
        }
    } catch (e) {
        _setTestBtnState('btnTestGemini', 'fail', 'Error');
    }
}

async function testDeepSeekKeyLive() {
    const keyInput = document.getElementById('deepseekApiKeyInput');
    const key = keyInput ? keyInput.value.trim() : '';

    if (!key) { _setTestBtnState('btnTestDeepSeek', 'warn', 'No Key'); return; }
    _setTestBtnState('btnTestDeepSeek', 'loading');

    try {
        const formData = new FormData();
        formData.append('api_key', key);
        formData.append('provider', 'deepseek');
        const res = await fetch('/api/test_llm_key', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.valid) {
            _setTestBtnState('btnTestDeepSeek', 'ok', 'Connected!');
        } else {
            _setTestBtnState('btnTestDeepSeek', 'fail', 'Invalid Key');
        }
    } catch (e) {
        _setTestBtnState('btnTestDeepSeek', 'fail', 'Error');
    }
}

async function testGroqKeyLive() {
    const keyInput = document.getElementById('groqApiKeyInput');
    const key = keyInput ? keyInput.value.trim() : '';

    if (!key) { _setTestBtnState('btnTestGroq', 'warn', 'No Key'); return; }
    _setTestBtnState('btnTestGroq', 'loading');

    try {
        const formData = new FormData();
        formData.append('api_key', key);
        formData.append('provider', 'groq');
        const res = await fetch('/api/test_llm_key', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.valid) {
            _setTestBtnState('btnTestGroq', 'ok', 'Connected!');
        } else {
            _setTestBtnState('btnTestGroq', 'fail', 'Invalid Key');
        }
    } catch (e) {
        _setTestBtnState('btnTestGroq', 'fail', 'Error');
    }
}

async function testOpenRouterKeyLive() {
    const keyInput = document.getElementById('openrouterApiKeyInput');
    const key = keyInput ? keyInput.value.trim() : '';

    if (!key) { _setTestBtnState('btnTestOpenRouter', 'warn', 'No Key'); return; }
    _setTestBtnState('btnTestOpenRouter', 'loading');

    try {
        const formData = new FormData();
        formData.append('api_key', key);
        formData.append('provider', 'openrouter');
        const res = await fetch('/api/test_llm_key', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.valid) {
            _setTestBtnState('btnTestOpenRouter', 'ok', 'Connected!');
        } else {
            _setTestBtnState('btnTestOpenRouter', 'fail', 'Invalid Key');
        }
    } catch (e) {
        _setTestBtnState('btnTestOpenRouter', 'fail', 'Error');
    }
}

async function testOpenAIKeyLive() {
    const keyInput = document.getElementById('openaiApiKeyInput');
    const key = keyInput ? keyInput.value.trim() : '';

    if (!key) { _setTestBtnState('btnTestOpenAI', 'warn', 'No Key'); return; }
    _setTestBtnState('btnTestOpenAI', 'loading');

    try {
        const formData = new FormData();
        formData.append('api_key', key);
        formData.append('provider', 'openai');
        const res = await fetch('/api/test_llm_key', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.valid) {
            _setTestBtnState('btnTestOpenAI', 'ok', 'Connected!');
        } else {
            _setTestBtnState('btnTestOpenAI', 'fail', 'Invalid Key');
        }
    } catch (e) {
        _setTestBtnState('btnTestOpenAI', 'fail', 'Error');
    }
}

let currentWorkflowMode = 'dubbing';

function onPrefWorkflowModeChange(val) {
    currentWorkflowMode = val;
    const styleGroup = document.getElementById('prefRecapStyleGroup');

    if (styleGroup) {
        if (val === 'recap') {
            styleGroup.style.opacity = '1';
            styleGroup.style.pointerEvents = 'auto';
        } else {
            styleGroup.style.opacity = '0.5';
            styleGroup.style.pointerEvents = 'none';
        }
    }

    updateUnifiedButtonState(isTranscribed ? 'transcribed' : 'initial');
}

function switchWorkflowMode(mode) {
    onPrefWorkflowModeChange(mode);
    const prefSelect = document.getElementById('prefWorkflowModeSelect');
    if (prefSelect) prefSelect.value = mode;
}

function handleUnifiedProcessClick() {
    if (isTranscribed) {
        startFinalProcess();
    } else {
        startTranscriptionOnly();
    }
}

// 4. Start Final Full Dubbing Process
async function startFinalProcess() {
    const fileInput = document.getElementById('videoFileInput');
    const fileToUpload = (fileInput && fileInput.files && fileInput.files.length > 0) ? fileInput.files[0] : loadedVideoFile;

    if (!currentJobId && !fileToUpload) {
        alert('Please select a video file or transcribe first!');
        return;
    }

    // An output folder must be chosen before the final render can start —
    // otherwise there's nowhere for the finished video to be saved to.
    let savedFolder = localStorage.getItem('userCustomSaveFolder') || '';
    if (!savedFolder) {
        savedFolder = await browseAndSetSaveFolder() || '';
    }
    if (!savedFolder) {
        alert('Please choose an output folder before starting the final render.');
        return;
    }

    const targetLang = document.getElementById('targetLangSelect') ? document.getElementById('targetLangSelect').value : 'km';
    const voiceId = document.getElementById('voiceSelect') ? document.getElementById('voiceSelect').value : 'auto';
    const whisperModel = document.getElementById('whisperModelSelect') ? document.getElementById('whisperModelSelect').value : 'base';
    const vocalMode = getSelectedVocalMode();
    const subToggleEl = document.getElementById('subToggle');
    const burnSubtitles = subToggleEl ? subToggleEl.checked : false;

    // Show progress modal overlay immediately
    showProgressSection('✨ Processing & Auto-Dubbing...', 'dub');

    const formData = new FormData();
    if (currentJobId) {
        formData.append('job_id', currentJobId);
    } else if (fileToUpload) {
        formData.append('video_file', fileToUpload);
    }

    const { rvcModel, rvcPitch } = getRvcModelParams();

    formData.append('target_lang', targetLang);
    formData.append('voice_id', voiceId);
    formData.append('whisper_model', whisperModel);
    formData.append('vocal_mode', vocalMode);
    formData.append('burn_subtitles', burnSubtitles);
    formData.append('rvc_model', rvcModel);
    formData.append('rvc_pitch', rvcPitch);

    // Primary AI model for context analyzer & translation cascade
    const primaryAiModelFinal = localStorage.getItem('primary_ai_model') || 'gemini';
    formData.append('primary_ai_model', primaryAiModelFinal);

    formData.append('output_path', savedFolder);



    const editedSegs = collectEditedSegments();
    if (editedSegs && editedSegs.length > 0) {
        formData.append('segments', JSON.stringify(editedSegs));
    }

    // Collect all video customization tab options
    const customEdits = collectCustomizationSettings();
    formData.append('custom_edits', JSON.stringify(customEdits));

    const logoInput = document.getElementById('logoFileInput');
    if (logoInput && logoInput.files && logoInput.files.length > 0) {
        formData.append('logo_file', logoInput.files[0]);
    }

    try {
        const response = await fetch('/api/process_file', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.job_id) {
            currentJobId = data.job_id;
            listenToProgress(data.job_id);
        } else {
            alert('Error: ' + (data.error || 'Failed to start final processing'));
            hideProgressSection();
        }
    } catch (err) {
        alert('Failed to start final process: ' + err.message);
        hideProgressSection();
    }
}

// 5. SSE Progress Listener
function listenToProgress(jobId) {
    if (eventSource) eventSource.close();

    eventSource = new EventSource(`/api/progress/${jobId}`);

    eventSource.onmessage = (event) => {
        const evtData = JSON.parse(event.data);
        updateProgressUI(evtData);

        if (evtData.status === 'transcribed' || evtData.status === 'completed') {
            eventSource.close();
            if (evtData.result_data) {
                currentJobData = evtData.result_data;
            }
            setTimeout(() => {
                hideProgressSection();
                if (evtData.status === 'transcribed') {
                    updateUnifiedButtonState('transcribed');
                    if (evtData.result_data) {
                        if (evtData.result_data.segments) {
                            renderTranscriptSegments(evtData.result_data.segments);
                            enableLiveSubtitles();
                        }
                        if (evtData.result_data.dubbed_audio_url) {
                            loadDubbedAudioTrack(evtData.result_data.dubbed_audio_url);
                        }
                    }
                    switchMainTab('transcript');
                } else if (evtData.result_data) {
                    showStudioSection(evtData.result_data);
                }
            }, 600);
        } else if (evtData.status === 'failed') {
            eventSource.close();
            alert('Dubbing process failed: ' + (evtData.error || evtData.message));
            hideProgressSection();
        }
    };

    eventSource.onerror = (err) => {
        console.error('SSE Error:', err);
    };
}


// Ordered step list for sequencing
const STEP_ORDER = ['extract_audio', 'transcribe', 'translate', 'tts_synthesis', 'merge_video'];

function appendActivityLog(msg) {
    const consoleEl = document.getElementById('activityLogConsole');
    if (!consoleEl) return;
    if (consoleEl.dataset.lastMsg === msg) return;
    consoleEl.dataset.lastMsg = msg;
    const timestamp = new Date().toLocaleTimeString();
    const formatted = msg.startsWith('[') ? msg : `[${timestamp}] ${msg}`;
    consoleEl.textContent += (consoleEl.textContent.trim() ? '\n' : '') + formatted;
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

function clearActivityLogs() {
    const consoleEl = document.getElementById('activityLogConsole');
    if (consoleEl) {
        consoleEl.textContent = `[System] Log output cleared at ${new Date().toLocaleTimeString()}.\n`;
        consoleEl.dataset.lastMsg = '';
    }
}

async function copyActivityLogs() {
    const consoleEl = document.getElementById('activityLogConsole');
    if (!consoleEl) return;
    try {
        await navigator.clipboard.writeText(consoleEl.textContent);
        if (typeof showToast === 'function') showToast('Activity logs copied to clipboard!', 'success');
        else alert('Activity logs copied to clipboard!');
    } catch (e) {
        alert('Failed to copy logs: ' + e.message);
    }
}

function updateProgressUI(data) {
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');
    const progressMessage = document.getElementById('progressMessage');

    const progress = data.progress || 0;
    if (progressBar) progressBar.style.width = `${progress}%`;
    if (progressPercent) progressPercent.textContent = `${progress}%`;
    if (progressMessage) {
        progressMessage.textContent = data.message || 'Processing...';
        appendActivityLog(`[${(data.step || 'INFO').toUpperCase()}] (${progress}%) ${data.message}`);
    }

    if (data.step) {
        const currentIdx = STEP_ORDER.indexOf(data.step);

        STEP_ORDER.forEach((stepKey, idx) => {
            const el = document.getElementById(`step_${stepKey}`);
            if (!el) return;

            if (idx < currentIdx) {
                // Previous steps — mark completed
                el.classList.remove('active');
                el.classList.add('completed');
            } else if (idx === currentIdx) {
                // Current step — active
                el.classList.add('active');
                el.classList.remove('completed');
            } else {
                // Future steps — clear
                el.classList.remove('active', 'completed');
            }
        });
    }
}

function showProgressSection(title, mode) {
    const modal = document.getElementById('progressSection');
    const titleEl = document.getElementById('progressTitle');
    const pct = document.getElementById('progressPercent');
    const bar = document.getElementById('progressBar');
    const msg = document.getElementById('progressMessage');
    const mergeStep = document.getElementById('step_merge_video');

    if (titleEl) titleEl.textContent = title || 'Processing...';
    if (pct) pct.textContent = '0%';
    if (bar) bar.style.width = '0%';
    if (msg) msg.textContent = 'Initializing...';

    document.querySelectorAll('.step-item').forEach(el => {
        el.classList.remove('active', 'completed');
    });


    // During transcription, hide the Video Merge step (only 4 steps shown)
    if (mergeStep) {
        if (mode === 'transcribe') {
            mergeStep.style.display = 'none';
        } else {
            mergeStep.style.display = '';
        }
    }

    if (modal) modal.classList.remove('hidden');
}

function hideProgressSection() {
    const modal = document.getElementById('progressSection');
    if (modal) modal.classList.add('hidden');
}

let confirmModalResolver = null;

function showCustomConfirm(title, message, options = {}) {
    return new Promise((resolve) => {
        confirmModalResolver = resolve;
        const modal = document.getElementById('confirmModal');
        const titleEl = document.getElementById('confirmModalTitle');
        const msgEl = document.getElementById('confirmModalMessage');
        const confirmBtn = document.getElementById('confirmModalConfirmBtn');
        const cancelBtn = document.getElementById('confirmModalCancelBtn');
        const iconEl = document.getElementById('confirmModalIcon');

        if (titleEl) titleEl.textContent = title || 'Confirm Action';
        if (msgEl) msgEl.textContent = message || 'Are you sure you want to proceed?';

        const confirmText = options.confirmText || 'Yes, Confirm';
        const cancelText = options.cancelText || 'Cancel';
        const isDanger = options.isDanger !== undefined ? options.isDanger : true;

        if (confirmBtn) {
            confirmBtn.innerHTML = isDanger ? `<i class="fa-solid fa-trash"></i> ${confirmText}` : `<i class="fa-solid fa-check"></i> ${confirmText}`;
            confirmBtn.style.background = isDanger ? 'linear-gradient(135deg, #ef4444, #dc2626)' : 'linear-gradient(135deg, #6366f1, #4f46e5)';
            confirmBtn.style.boxShadow = isDanger ? '0 4px 14px rgba(239,68,68,0.35)' : '0 4px 14px rgba(99,102,241,0.35)';
        }
        if (cancelBtn) {
            cancelBtn.innerHTML = `<i class="fa-solid fa-xmark"></i> ${cancelText}`;
        }
        if (iconEl) {
            iconEl.style.color = isDanger ? '#ef4444' : '#6366f1';
        }

        if (modal) modal.classList.remove('hidden');
    });
}

function closeCustomConfirm(result) {
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.add('hidden');
    if (confirmModalResolver) {
        confirmModalResolver(result);
        confirmModalResolver = null;
    }
}

let promptModalResolver = null;

function showCustomPrompt(title, defaultValue = '', placeholder = 'Enter name...') {
    return new Promise((resolve) => {
        promptModalResolver = resolve;
        const modal = document.getElementById('promptModal');
        const titleEl = document.getElementById('promptModalTitle');
        const inputEl = document.getElementById('promptModalInput');

        if (titleEl) titleEl.textContent = title || 'Enter Value';
        if (inputEl) {
            inputEl.value = defaultValue || '';
            inputEl.placeholder = placeholder || 'Enter name...';
        }

        if (modal) modal.classList.remove('hidden');
        if (inputEl) {
            setTimeout(() => {
                inputEl.focus();
                inputEl.select();
            }, 50);
        }
    });
}

function closeCustomPrompt(result) {
    const modal = document.getElementById('promptModal');
    if (modal) modal.classList.add('hidden');
    if (promptModalResolver) {
        promptModalResolver(result !== null && result !== undefined ? String(result).trim() : null);
        promptModalResolver = null;
    }
}

// Override native window.prompt and window.confirm to prevent default browser popups
window.prompt = function(message, defaultValue) {
    showCustomPrompt(message, defaultValue);
    return null;
};

async function cancelProcessingJob() {
    const confirmed = await showCustomConfirm(
        "Cancel Processing Task?",
        "Are you sure you want to cancel the active video processing task? Progress will be stopped."
    );
    if (confirmed) {
        hideProgressSection();
        if (window.activeEventSource) {
            try { window.activeEventSource.close(); } catch (e) {}
            window.activeEventSource = null;
        }
        if (typeof showToast === 'function') {
            showToast('Processing task canceled', 'warning');
        }
    }
}

// 6. Show Output Studio View
function showStudioSection(result) {
    document.getElementById('progressSection').classList.add('hidden');
    document.getElementById('studioSection').classList.remove('hidden');

    const player = document.getElementById('outputVideoPlayer');
    const videoSource = document.getElementById('videoSource');
    const subtitleTrack = document.getElementById('subtitleTrack');
    const placeholder = document.getElementById('videoPlaceholder');
    const badge = document.getElementById('playerStatusBadge');

    // Reveal the video player (was showing placeholder before)
    if (placeholder) placeholder.classList.add('hidden');
    if (player) player.classList.remove('hidden');

    // Update badge to "Dubbed Ready"
    if (badge) {
        badge.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Dubbed Ready';
        badge.className = 'badge badge-success';
    }

    if (result) {
        const dubbedUrl = result.dubbed_video_url || result.output_video_url || result.video_url;
        if (dubbedUrl && videoSource) {
            if (player) player.removeAttribute('src'); // guard: a stray direct src would make this <source> swap a no-op
            videoSource.src = dubbedUrl;
        }
    }


    if (subtitleTrack) {
        subtitleTrack.removeAttribute('src');
        subtitleTrack.src = '';
    }

    player.load();
    updateLivePreviewOverlays();

    // Show audio track toggle and download buttons (hidden at first launch)
    const audioSel = document.getElementById('audioTrackSelector');
    const dlGrid = document.getElementById('downloadGrid');
    if (audioSel) audioSel.classList.remove('hidden');
    if (dlGrid) dlGrid.classList.remove('hidden');

    // Scroll to process button if present
    const unifiedBtn = document.getElementById('unifiedProcessBtn');
    if (unifiedBtn) {
        unifiedBtn.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
}

function backToMainWindow() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function browseAndSetSaveFolder() {
    try {
        let folder = '';
        if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.select_folder === 'function') {
            folder = await window.pywebview.api.select_folder();
        } else {
            const res = await fetch('/api/browse_folder', { method: 'POST' });
            const data = await res.json();
            folder = data.folder || '';
        }

        if (folder) {
            localStorage.setItem('userCustomSaveFolder', folder);

            const batchInput = document.getElementById('batchOutputFolderInput');
            if (batchInput) batchInput.value = folder;

            if (typeof showToast === 'function') {
                showToast(`📁 Save directory set: ${folder}`, 'success');
            } else {
                console.log('Output directory set:', folder);
            }
            return folder;
        }
    } catch (e) {
        console.warn('Failed to browse folder:', e);
    }
    return '';
}

async function openOutputFolder(jobId) {
    try {
        const id = jobId || (typeof currentJobId !== 'undefined' ? currentJobId : '');
        const res = await fetch('/api/open_output_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: id })
        });
        const data = await res.json();
        if (data.error) {
            alert('Could not open output folder: ' + data.error);
        }
    } catch (e) {
        alert('Failed to open output folder: ' + e.message);
    }
}

// Download: native Save dialog inside pywebview window, or browser download
async function triggerDownload(type) {
    if (!currentJobId) {
        alert('No active job found!');
        return;
    }

    // Running inside pywebview native window → use native Save As dialog
    if (window.pywebview && window.pywebview.api) {
        try {
            const result = await window.pywebview.api.save_file(currentJobId, type);
            if (result && result.ok) {
                console.log('Saved to:', result.path);
            } else if (result && result.error && result.error !== 'Cancelled') {
                alert('Save failed: ' + result.error);
            }
        } catch (err) {
            alert('Save error: ' + err);
        }
        return;
    }

    // Running in normal browser → redirect to Flask download endpoint
    window.location.href = `/api/download/${currentJobId}/${type}`;
}

// ─── Import & Export SRT Subtitle Feature ────────────────────────────────────
function triggerImportSRT() {
    const input = document.getElementById('srtFileInput');
    if (input) input.click();
}

async function handleImportSRTFile(input) {
    if (!input || !input.files || input.files.length === 0) return;
    const file = input.files[0];

    const formData = new FormData();
    formData.append('srt_file', file);
    if (currentJobId) {
        formData.append('job_id', currentJobId);
    }

    try {
        const res = await fetch('/api/import_srt', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.error) {
            alert('Import SRT error: ' + data.error);
            return;
        }

        currentJobId = data.job_id;
        if (!currentJobData) currentJobData = {};
        currentJobData.job_id = data.job_id;
        currentJobData.segments = data.segments;
        currentJobData.srt_url = data.srt_url;

        // Populate transcript cards UI
        const placeholder = document.getElementById('emptyTranscriptPlaceholder');
        const segsList = document.getElementById('segmentsList');
        if (placeholder) placeholder.classList.add('hidden');
        if (segsList) segsList.classList.remove('hidden');

        renderTranscriptCards(data.segments);

        const countSpan = document.getElementById('transcriptSegCount');
        if (countSpan) countSpan.textContent = `${data.segments.length} segments imported`;

        // Imported SRT already has final segment timing/text -- skip straight to
        // "Final Process" instead of leaving the button on "Transcript" (which
        // would re-run transcription/translation on the video unnecessarily).
        updateUnifiedButtonState('transcribed');
        enableLiveSubtitles();

        updateLivePreviewOverlays();


    } catch (e) {
        alert('Failed to import SRT file: ' + e.message);
    } finally {
        input.value = '';
    }
}

function exportCurrentSRT() {
    if (!currentJobData || !currentJobData.segments || currentJobData.segments.length === 0) {
        if (currentJobId) {
            triggerDownload('srt');
            return;
        }
        alert('No subtitle segments available to export! Please transcribe audio or import an SRT first.');
        return;
    }

    const segs = currentJobData.segments;
    let srtText = '';

    segs.forEach((seg, idx) => {
        const input = document.getElementById(`trans_input_${seg.id}`) || document.getElementById(`segInput_${idx}`);
        const text = input ? input.value : (seg.translated_text || seg.original_text || '');
        
        function formatSrtTime(s) {
            const h = Math.floor(s / 3600);
            const m = Math.floor((s % 3600) / 60);
            const sec = Math.floor(s % 60);
            const ms = Math.round((s - Math.floor(s)) * 1000);
            return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')},${ms.toString().padStart(3, '0')}`;
        }

        srtText += `${idx + 1}\n${formatSrtTime(seg.start)} --> ${formatSrtTime(seg.end)}\n${text}\n\n`;
    });

    if (currentJobId && window.pywebview && window.pywebview.api) {
        triggerDownload('srt');
        return;
    }

    const blob = new Blob([srtText], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const baseName = currentJobData.original_base || 'subtitles';
    a.download = `${baseName}_dubbed.srt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function fixKhmerSpelling(str) {
    if (!str) return '';
    let text = String(str);
    text = text.replace(/\s*[\u17d2]\s*/g, '\u17d2');
    text = text.replace(/\s+([\u17b4-\u17d3])/g, '$1');
    text = text.replace(/\u25cc/g, '');
    text = text.replace(/\u17d4/g, '');
    return text.trim();
}

function splitLongSegmentsByPunctuation(segments) {
    if (!segments || !Array.isArray(segments)) return segments;

    const newSegments = [];
    const punctRegex = /[^\u17d4?\.,]+[\u17d4?\.,]?/g;

    segments.forEach(seg => {
        const st = parseFloat(seg.start || 0);
        const et = parseFloat(seg.end || 0);
        const txt = String(seg.translated_text || seg.text || '').trim();

        if (!txt || et <= st) return;

        const chunks = (txt.match(punctRegex) || []).map(c => c.trim()).filter(c => c.length > 0);

        if (chunks.length <= 1 || (txt.length <= 30 && chunks.length <= 1)) {
            newSegments.push(seg);
            return;
        }

        const totalDuration = et - st;
        const totalLen = chunks.reduce((acc, c) => acc + c.length, 0);
        if (totalLen === 0) {
            newSegments.push(seg);
            return;
        }

        let currSt = st;
        chunks.forEach((chunk, idx) => {
            const frac = chunk.length / totalLen;
            let chunkDur = Math.max(0.8, totalDuration * frac);
            let chunkEt = currSt + chunkDur;
            if (idx === chunks.length - 1) chunkEt = et;
            if (chunkEt <= currSt) chunkEt = currSt + 1.0;

            newSegments.push({
                ...seg,
                id: newSegments.length + 1,
                start: parseFloat(currSt.toFixed(2)),
                end: parseFloat(chunkEt.toFixed(2)),
                original_text: chunk,
                translated_text: chunk,
                text: chunk
            });

            currSt = parseFloat((chunkEt + 0.05).toFixed(2));
        });
    });

    return newSegments;
}

// 7. Render Transcript Segment List (Compact Inline Rows)
function renderTranscriptCards(rawSegments) {
    const container = document.getElementById('segmentsList') || document.getElementById('segmentsContainer');
    const placeholder = document.getElementById('emptyTranscriptPlaceholder');
    if (!container) return;

    container.innerHTML = '';
    if (placeholder) placeholder.classList.add('hidden');
    container.classList.remove('hidden');

    const segments = splitLongSegmentsByPunctuation(rawSegments);
    if (!segments || !Array.isArray(segments)) return;

    if (currentJobData) currentJobData.segments = segments;

    const countSpan = document.getElementById('transcriptSegCount');
    if (countSpan) {
        countSpan.textContent = `${segments.length} segments`;
    }

    segments.forEach((seg, idx) => {
        const row = document.createElement('div');
        row.className = 'segment-row';
        row.id = `segRow_${idx}`;
        const rawTxt = seg.translated_text || seg.text || '';
        const txt = fixKhmerSpelling(rawTxt);
        seg.translated_text = txt;
        const segId = seg.id || (idx + 1);

        // Gender pill: Female ↔ Male only (no auto state)
        // Backend stamps seg.gender from the detected voice; default Female if missing.
        const gender = (seg.gender === 'Male') ? 'Male' : 'Female';
        const genderIcon  = gender === 'Female' ? '♀' : '♂';
        const genderClass = `seg-gender-btn seg-gender-${gender.toLowerCase()}`;
        const genderTitle = gender === 'Female' ? 'Female voice — click to switch to Male' : 'Male voice — click to switch to Female';
        // Keep in-memory segment in sync
        seg.gender = gender;

        row.innerHTML = `
            <span class="segment-time-badge">[${formatTime(seg.start)} - ${formatTime(seg.end)}]</span>
            <input type="text" class="segment-input-line" id="segInput_${idx}" data-id="${segId}" value="${escapeHtml(txt)}" data-idx="${idx}" placeholder="Translated text...">
            <button class="${genderClass}" id="segGender_${idx}" data-idx="${idx}" data-gender="${gender}" onclick="cycleSegmentGender(${idx})" title="${genderTitle}">${genderIcon}</button>
            <button class="segment-audio-btn" onclick="previewSegmentSpeech(${idx})" title="Listen preview">
                <i class="fa-solid fa-volume-high"></i>
            </button>
        `;
        container.appendChild(row);
    });
}

function cycleSegmentGender(idx) {
    const btn = document.getElementById(`segGender_${idx}`);
    if (!btn) return;
    // Toggle directly between Female and Male — no auto state
    const next  = btn.dataset.gender === 'Female' ? 'Male' : 'Female';
    const icon  = next === 'Female' ? '♀' : '♂';
    const title = next === 'Female' ? 'Female voice — click to switch to Male' : 'Male voice — click to switch to Female';
    btn.dataset.gender = next;
    btn.textContent    = icon;
    btn.title          = title;
    btn.className      = `seg-gender-btn seg-gender-${next.toLowerCase()}`;
    // Update in-memory segment
    if (currentJobData && currentJobData.segments && currentJobData.segments[idx]) {
        currentJobData.segments[idx].gender = next;
    }
}

// Preview Voice Functions
async function previewSelectedVoice(mode) {
    const targetLang = document.getElementById('targetLangSelect')?.value || 'km';
    const voiceId    = document.getElementById('voiceSelect')?.value || 'auto';
    const { rvcModel, rvcPitch } = getRvcModelParams();

    const btnId = (mode === 'rvc') ? 'btnPreviewRvcVoice' : 'btnPreviewNeuralVoice';
    const btn   = document.getElementById(btnId);
    const originalHtml = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generating...';
    }

    try {
        const endpoint = (mode === 'rvc' && rvcModel !== 'none') ? '/api/preview_rvc_with_sample' : '/api/preview_voice';
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target_lang: targetLang,
                voice_id: voiceId,
                rvc_model: rvcModel,
                rvc_pitch: rvcPitch
            })
        });

        const data = await res.json();
        if (data.ok && data.audio) {
            if (window.currentAudioPreview) {
                window.currentAudioPreview.pause();
            }
            window.currentAudioPreview = new Audio(data.audio);
            window.currentAudioPreview.play();
        } else {
            alert(`Preview failed: ${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Preview error: ${e.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
}

async function previewSegmentSpeech(idx) {
    if (window.currentAudioPreview) {
        window.currentAudioPreview.pause();
        window.currentAudioPreview = null;
    }

    const inputEl = document.getElementById(`segInput_${idx}`);
    const seg = (currentJobData && currentJobData.segments) ? currentJobData.segments[idx] : null;
    const text = inputEl ? inputEl.value.trim() : (seg ? (seg.translated_text || '') : '');

    if (!text) return;

    // Read gender for THIS specific segment row
    const genderBtn = document.getElementById(`segGender_${idx}`);
    const segGender = genderBtn ? genderBtn.dataset.gender : (seg?.gender || 'Female');

    const targetLang = document.getElementById('targetLangSelect')?.value || 'km';

    // Resolve gender → voice ID
    let voiceId = 'auto';
    if (segGender && window._voicesByLang && window._voicesByLang[targetLang]) {
        const match = window._voicesByLang[targetLang].find(
            v => v.gender && v.gender.toLowerCase() === segGender.toLowerCase()
        );
        if (match) voiceId = match.id;
    }
    if (voiceId === 'auto') {
        voiceId = document.getElementById('voiceSelect')?.value || 'auto';
    }

    // Check RVC Voice Cloning state
    const { rvcModel, rvcPitch } = getRvcModelParams();

    const rowBtn = document.querySelector(`#segRow_${idx} .segment-audio-btn i`);
    if (rowBtn) {
        rowBtn.className = 'fa-solid fa-spinner fa-spin';
    }

    try {
        const res = await fetch('/api/preview_voice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                target_lang: targetLang,
                voice_id: voiceId,
                gender: segGender,
                text: text,
                rvc_model: rvcModel,
                rvc_pitch: rvcPitch
            })
        });
        const data = await res.json();
        if (data.ok && data.audio) {
            if (window.currentAudioPreview) {
                window.currentAudioPreview.pause();
            }
            window.currentAudioPreview = new Audio(data.audio);
            await window.currentAudioPreview.play();
        } else {
            alert(`Segment preview failed: ${data.error || 'Unknown error'}`);
        }
    } catch (e) {
        alert(`Preview error: ${e.message}`);
    } finally {
        if (rowBtn) {
            rowBtn.className = 'fa-solid fa-volume-high';
        }
    }
}


function seekVideo(timeSec) {
    const player = document.getElementById('outputVideoPlayer');
    player.currentTime = timeSec;
    player.play();
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 8. Dual Audio Track Switcher
function switchAudioTrack(trackType) {
    const player = document.getElementById('outputVideoPlayer');
    const dubbedBtn = document.getElementById('trackDubbedBtn');
    const origBtn = document.getElementById('trackOriginalBtn');

    if (!currentJobData) return;

    const currentTime = player.currentTime;
    const isPlaying = !player.paused;

    player.removeAttribute('src'); // guard: a stray direct src would make this <source> swap a no-op

    if (trackType === 'dubbed') {
        dubbedBtn.classList.add('active');
        origBtn.classList.remove('active');
        document.getElementById('videoSource').src = currentJobData.video_url;
    } else {
        origBtn.classList.add('active');
        dubbedBtn.classList.remove('active');
        document.getElementById('videoSource').src = currentJobData.original_audio_url ? currentJobData.video_url : currentJobData.video_url;
    }

    player.load();
    player.currentTime = currentTime;
    if (isPlaying) player.play();
}

function previewLogoName(input) {
    handleLogoSelect(input);
}

function handleLogoSelect(input) {
    const label = document.getElementById('logoFileName');
    const liveLogoOverlay = document.getElementById('liveLogoOverlay');
    const liveLogoImg = document.getElementById('liveLogoImg');

    if (input.files && input.files[0]) {
        const file = input.files[0];
        if (label) {
            label.textContent = file.name;
            label.style.color = '#38bdf8';
        }
        if (liveLogoImg) {
            liveLogoImg.src = URL.createObjectURL(file);
        }
        if (liveLogoOverlay) {
            liveLogoOverlay.classList.remove('hidden');
        }
    } else {
        if (label) {
            label.textContent = 'No logo selected';
            label.style.color = 'var(--text-muted)';
        }
    }
}

function resetColorAdjustment() {
    const br = document.getElementById('colorBrightness');
    const ct = document.getElementById('colorContrast');
    const st = document.getElementById('colorSaturation');
    const hue = document.getElementById('colorHue');

    if (br) br.value = 0;
    if (ct) ct.value = 100;
    if (st) st.value = 100;
    if (hue) hue.value = 0;

    updateLivePreviewOverlays();
}

// 9. Studio Tab Switcher
function switchStudioTab(tabId) {
    const panels = {
        'mirror': 'panelMirror',
        'crop': 'panelMirror',
        'blur': 'panelBlur',
        'subtitles': 'panelSubtitles',
        'text': 'panelText',
        'logo': 'panelLogo',
        'pip': 'panelPip',
        'color': 'panelColor'
    };

    // Update active tab buttons
    document.querySelectorAll('.studio-tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.getAttribute('onclick').includes(`'${tabId}'`)) {
            btn.classList.add('active');
        }
    });

    // Update active tab panel
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.remove('active');
    });

    const targetPanelId = panels[tabId] || 'panelBlur';
    const targetPanel = document.getElementById(targetPanelId);
    if (targetPanel) {
        targetPanel.classList.add('active');
    }

    // Switching tabs doesn't change any slider/toggle value, but the overlays these tabs
    // control (blur box, subtitles, text, logo) are all stacked on the video at once and
    // need to reflect whatever the inputs on the newly-shown tab currently hold — without
    // this, the preview could still be showing state from before the tab switch.
    updateLivePreviewOverlays();
}

// Recompute overlay sizing whenever the window is resized (the preview box flips between
// 552px and 430px at the 992px breakpoint — font % needs to be reapplied against real height).
window.addEventListener('resize', () => updateLivePreviewOverlays());

function selectPresetCard(presetName) {
    const sel = document.getElementById('subStylePreset');
    if (sel) {
        sel.value = presetName;
    }
    ['Outline', 'YellowBox', 'WhiteText', 'Glow'].forEach(p => {
        const card = document.getElementById(`cardPreset${p}`);
        if (card) {
            if (p === presetName) {
                card.style.border = '2px solid #6366f1';
                card.style.boxShadow = '0 0 12px rgba(99, 102, 241, 0.4)';
            } else {
                card.style.border = '1px solid var(--border-color)';
                card.style.boxShadow = 'none';
            }
        }
    });
    updateLivePreviewOverlays();
}

// 10. Real-time Live Canvas Overlays Engine
function updateLivePreviewOverlays() {
    const player = document.getElementById('outputVideoPlayer');
    const isVideoLoaded = loadedVideoFile || (player && player.src && !player.classList.contains('hidden'));

    // Always update numeric slider label displays
    const blurPosY = document.getElementById('blurPosY');
    const blurHeight = document.getElementById('blurHeight');
    const blurPosX = document.getElementById('blurPosX');
    const blurWidth = document.getElementById('blurWidth');
    const blurOpacity = document.getElementById('blurOpacity');

    if (blurPosY) document.getElementById('valBlurPosY').textContent = blurPosY.value + '%';
    if (blurHeight) document.getElementById('valBlurHeight').textContent = blurHeight.value + '%';
    if (blurPosX) document.getElementById('valBlurPosX').textContent = blurPosX.value + '%';
    if (blurWidth) document.getElementById('valBlurWidth').textContent = blurWidth.value + '%';
    if (blurOpacity) document.getElementById('valBlurOpacity').textContent = blurOpacity.value + '%';

    const subSize = document.getElementById('subSize');
    const subTextOpacity = document.getElementById('subTextOpacity');
    const subOutline = document.getElementById('subOutline');
    const subPos = document.getElementById('subPos');

    if (subSize) document.getElementById('valSubSize').textContent = subSize.value + 'px';
    if (subTextOpacity) document.getElementById('valSubTextOpacity').textContent = subTextOpacity.value + '%';
    if (subOutline) document.getElementById('valSubOutline').textContent = subOutline.value + 'px';
    if (subPos) document.getElementById('valSubPos').textContent = subPos.value + '%';

    const textSpeed = document.getElementById('textSpeed');
    const textSize = document.getElementById('textSize');
    const textBgOpacity = document.getElementById('textBgOpacity');
    const textOpacity = document.getElementById('textOpacity');
    const textOutlineWidth = document.getElementById('textOutlineWidth');
    const textShadow = document.getElementById('textShadow');
    const textPosY = document.getElementById('textPosY');

    if (textSpeed) document.getElementById('valTextSpeed').textContent = textSpeed.value + 's';
    if (textSize) document.getElementById('valTextSize').textContent = textSize.value + 'px';
    if (textBgOpacity) document.getElementById('valTextBgOpacity').textContent = textBgOpacity.value + '%';
    if (textOpacity) document.getElementById('valTextOpacity').textContent = textOpacity.value + '%';
    if (textOutlineWidth) document.getElementById('valTextOutlineWidth').textContent = textOutlineWidth.value + 'px';
    if (textShadow) document.getElementById('valTextShadow').textContent = textShadow.value + 'px';
    if (textPosY) { const el = document.getElementById('valTextPosY'); if (el) el.textContent = textPosY.value + '%'; }

    const logoSize = document.getElementById('logoSize');
    const logoOpacity = document.getElementById('logoOpacity');
    const logoRadius = document.getElementById('logoRadius');
    const logoShadow = document.getElementById('logoShadow');

    if (logoSize) document.getElementById('valLogoSize').textContent = logoSize.value + '%';
    if (logoOpacity) document.getElementById('valLogoOpacity').textContent = logoOpacity.value + '%';
    if (logoRadius) document.getElementById('valLogoRadius').textContent = logoRadius.value + 'px';
    if (logoShadow) document.getElementById('valLogoShadow').textContent = logoShadow.value + 'px';

    const pipSize = document.getElementById('pipSize');
    const pipOpacity = document.getElementById('pipOpacity');

    if (pipSize) { const el = document.getElementById('valPipSize'); if (el) el.textContent = pipSize.value + '%'; }
    if (pipOpacity) { const el = document.getElementById('valPipOpacity'); if (el) el.textContent = pipOpacity.value + '%'; }

    const colorBrightness = document.getElementById('colorBrightness');
    const colorContrast = document.getElementById('colorContrast');
    const colorSaturation = document.getElementById('colorSaturation');
    const colorHue = document.getElementById('colorHue');

    if (colorBrightness) document.getElementById('valColorBrightness').textContent = colorBrightness.value;
    if (colorContrast) document.getElementById('valColorContrast').textContent = colorContrast.value + '%';
    if (colorSaturation) document.getElementById('valColorSaturation').textContent = colorSaturation.value + '%';
    if (colorHue) document.getElementById('valColorHue').textContent = colorHue.value + '°';

    // If no video is loaded yet, keep live canvas overlays hidden over placeholder
    if (!isVideoLoaded) {
        ['liveBlurOverlay', 'liveTextOverlay', 'liveLogoOverlay', 'liveSubOverlay'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.add('hidden');
        });
        return;
    }

    // 0. Mirror & Color Video Effects on Player
    const mirrorToggle = document.getElementById('mirrorToggle');
    const colorToggle = document.getElementById('colorToggle');
    const playerVideo = document.getElementById('outputVideoPlayer');
    if (playerVideo) {
        if (mirrorToggle && mirrorToggle.checked) {
            playerVideo.style.transform = 'scaleX(-1)';
        } else {
            playerVideo.style.transform = 'none';
        }

        let filters = [];
        if (colorToggle && colorToggle.checked) {
            const br = colorBrightness ? parseFloat(colorBrightness.value) : 0;
            const ct = colorContrast ? parseFloat(colorContrast.value) : 100;
            const st = colorSaturation ? parseFloat(colorSaturation.value) : 100;
            const hue = colorHue ? parseFloat(colorHue.value) : 0;
            filters.push(`brightness(${1 + br / 100})`);
            filters.push(`contrast(${ct / 100})`);
            filters.push(`saturate(${st / 100})`);
            filters.push(`hue-rotate(${hue}deg)`);
        }
        playerVideo.style.filter = filters.length > 0 ? filters.join(' ') : 'none';
    }

    // 1. Blur Box Overlay
    const blurToggle = document.getElementById('blurToggle');
    const liveBlur = document.getElementById('liveBlurOverlay');

    if (liveBlur) {
        if (blurToggle && blurToggle.checked) {
            liveBlur.classList.remove('hidden');
            const posY   = Math.min(Math.max(blurPosY   ? parseFloat(blurPosY.value)   : 57.3, 0), 95);
            const height = Math.min(Math.max(blurHeight  ? parseFloat(blurHeight.value) : 7,    1), 100 - posY);
            const posX   = Math.min(Math.max(blurPosX   ? parseFloat(blurPosX.value)   : 0,    0), 95);
            const width  = Math.min(Math.max(blurWidth   ? parseFloat(blurWidth.value)  : 100,  1), 100 - posX);
            liveBlur.style.top     = posY + '%';
            liveBlur.style.height  = height + '%';
            liveBlur.style.left    = posX + '%';
            liveBlur.style.width   = width + '%';
            liveBlur.style.opacity = (blurOpacity ? blurOpacity.value / 100 : 1);
        } else {
            liveBlur.classList.add('hidden');
        }
    }

    // 2. Subtitles Overlay & Native Player Track Toggle
    const subToggle     = document.getElementById('subToggle');
    const liveSub       = document.getElementById('liveSubOverlay');
    const subFont       = document.getElementById('subFont');
    const subPreset     = document.getElementById('subStylePreset');
    const playerElement = document.getElementById('outputVideoPlayer');
    const subtitleTrack = document.getElementById('subtitleTrack');

    const isSubEnabled = subToggle && subToggle.checked;

    if (subtitleTrack) {
        subtitleTrack.removeAttribute('src');
        subtitleTrack.src = '';
    }
    if (playerElement && playerElement.textTracks && playerElement.textTracks.length > 0) {
        for (let i = 0; i < playerElement.textTracks.length; i++) {
            playerElement.textTracks[i].mode = 'disabled';
        }
    }

    if (liveSub) {
        if (isSubEnabled) {
            liveSub.classList.remove('hidden');
            liveSubEnabled = true;
            clearSubtitlePreviewCache(); // force re-render preview overlay on control change

            const player = document.getElementById('outputVideoPlayer');
            const currTime = player ? player.currentTime : 0;
            let currentText = 'Sample Subtitle Text';

            if (currentJobData && currentJobData.segments) {
                const segs = currentJobData.segments;
                for (let i = 0; i < segs.length; i++) {
                    if (currTime >= segs[i].start && currTime <= segs[i].end) {
                        const segId = segs[i].id || (i + 1);
                        const input = document.getElementById(`trans_input_${segId}`) || document.getElementById(`segInput_${i}`) || document.getElementById(`trans_input_${i}`);
                        currentText = input ? input.value : (segs[i].translated_text || segs[i].text || '');
                        break;
                    }
                }
                if (currentText === 'Sample Subtitle Text' && segs.length > 0) {
                    const input = document.getElementById(`trans_input_1`) || document.getElementById(`segInput_0`);
                    currentText = input ? input.value : (segs[0].translated_text || segs[0].text || 'Sample Subtitle Text');
                }
            }

            fetchPythonLivePreviewOverlay(currentText);
        } else {
            liveSub.classList.add('hidden');
            liveSubEnabled = false;
        }
    }

    // 3. Custom Text Overlay Banner
    const textToggle   = document.getElementById('textToggle');
    const overlayText  = document.getElementById('overlayText');
    const liveText     = document.getElementById('liveTextOverlay');
    const textFont     = document.getElementById('textFont');

    if (liveText) {
        if (textToggle && textToggle.checked && overlayText && overlayText.value.trim()) {
            liveText.classList.remove('hidden');
            liveText.style.display = 'inline-block';
            
            const fontTextInfo = getSelectedFont('textFont');
            const fontTextName = fontTextInfo && fontTextInfo.name ? fontTextInfo.name : (textFont && textFont.value ? textFont.value : 'Kantumruy Pro');
            liveText.textContent = overlayText.value.replace(/'/g, '\u2019');
            liveText.style.setProperty('font-family', `"${fontTextName}", sans-serif`, 'important');

            const textCfg = collectCustomizationSettings().text;

            // 1. Font Size & Style
            const sizeVal = textCfg.size; // size in px
            liveText.style.fontSize = sizeVal + 'px';
            liveText.style.fontWeight = textCfg.bold ? 'bold' : 'normal';
            liveText.style.fontStyle = textCfg.italic ? 'italic' : 'normal';

            // 2. Colors & Opacity
            liveText.style.color = textCfg.color_fill;
            liveText.style.opacity = (textCfg.opacity / 100).toString();

            // Background box & bg opacity
            const hexToRgba = (hex, alpha) => {
                let c = (hex || '#808080').replace('#', '');
                if (c.length === 3) c = c.split('').map(x => x + x).join('');
                const num = parseInt(c, 16);
                return `rgba(${(num >> 16) & 255}, ${(num >> 8) & 255}, ${num & 255}, ${alpha})`;
            };
            const bgAlpha = textCfg.bg_opacity / 100;
            liveText.style.backgroundColor = bgAlpha > 0 ? hexToRgba(textCfg.color_bg, bgAlpha) : 'transparent';
            liveText.style.padding = bgAlpha > 0 ? '4px 14px' : '2px 6px';
            liveText.style.borderRadius = '6px';

            // 3. Outline & Shadow
            const outlineW = textCfg.outline;
            if (outlineW > 0) {
                const oColor = textCfg.color_outline || '#FFFFFF';
                liveText.style.webkitTextStroke = `${outlineW}px ${oColor}`;
                liveText.style.textShadow = `-1px -1px 0 ${oColor}, 1px -1px 0 ${oColor}, -1px 1px 0 ${oColor}, 1px 1px 0 ${oColor}`;
            } else {
                liveText.style.webkitTextStroke = '0px transparent';
                liveText.style.textShadow = 'none';
            }

            const shadowW = textCfg.shadow;
            if (shadowW > 0) {
                liveText.style.filter = `drop-shadow(0px ${shadowW}px ${shadowW}px rgba(0, 0, 0, 0.75))`;
            } else {
                liveText.style.filter = 'none';
            }

            // 4. Animation & Loop
            const animType = textCfg.anim;
            const speedSec = textCfg.speed || 10;
            const isLoop = textCfg.loop;
            const loopMode = isLoop ? 'infinite' : 'forwards';

            if (animType === 'slide_top') {
                liveText.style.animation = `textSlideTop ${speedSec}s linear ${loopMode}`;
            } else if (animType === 'slide_bottom') {
                liveText.style.animation = `textSlideBottom ${speedSec}s linear ${loopMode}`;
            } else if (animType === 'slide_left') {
                liveText.style.animation = `textSlideLeft ${speedSec}s linear ${loopMode}`;
            } else if (animType === 'fade') {
                liveText.style.animation = `textFadeInOut ${speedSec}s ease-in-out ${loopMode}`;
            } else if (animType === 'pulse') {
                liveText.style.animation = `textPulse ${speedSec}s ease-in-out ${loopMode}`;
            } else if (animType === 'bounce') {
                liveText.style.animation = `textBounce ${speedSec}s ease-in-out ${loopMode}`;
            } else {
                liveText.style.animation = 'none';
                liveText.style.top = textCfg.posY + '%';
            }
        } else {
            liveText.classList.add('hidden');
            liveText.style.display = 'none';
        }
    }


    // 4. Logo Watermark Overlay
    const logoToggle  = document.getElementById('logoToggle');
    const liveLogo    = document.getElementById('liveLogoOverlay');
    const liveLogoImg = document.getElementById('liveLogoImg');

    if (liveLogo) {
        if (logoToggle && logoToggle.checked && liveLogoImg && liveLogoImg.src && liveLogoImg.src !== window.location.href) {
            liveLogo.classList.remove('hidden');
            liveLogo.style.width        = Math.min(logoSize ? parseFloat(logoSize.value) : 54, 90) + '%';
            liveLogo.style.opacity      = (logoOpacity ? logoOpacity.value / 100 : 0.1);
            liveLogo.style.borderRadius = (logoRadius ? logoRadius.value : 0) + 'px';
        } else {
            liveLogo.classList.add('hidden');
        }
    }
}

async function autoDetectCaptionRegion() {
    const btn = document.getElementById('autoDetectBlurBtn');
    let videoFileObj = null;
    let videoPath = '';

    // 1. Check loadedVideoFile global
    if (typeof loadedVideoFile !== 'undefined' && loadedVideoFile) {
        videoFileObj = loadedVideoFile;
        if (loadedVideoFile.path) videoPath = loadedVideoFile.path;
    }

    // 2. Check single video file input
    if (!videoPath && !videoFileObj) {
        const singleFileInput = document.getElementById('videoFileInput');
        if (singleFileInput && singleFileInput.files && singleFileInput.files[0]) {
            videoFileObj = singleFileInput.files[0];
            if (singleFileInput.files[0].path) videoPath = singleFileInput.files[0].path;
        }
    }

    // 3. Check batch queue
    if (!videoPath && !videoFileObj && typeof batchQueue !== 'undefined' && batchQueue.length > 0) {
        const queuedItem = batchQueue.find(i => i.filePath || i.file);
        if (queuedItem) {
            videoPath = queuedItem.filePath || (queuedItem.file ? queuedItem.file.path : '');
            videoFileObj = queuedItem.file || null;
        }
    }

    if (!videoPath && !videoFileObj) {
        if (typeof showToast === 'function') {
            showToast('⚠️ Please load or add a video file first to auto-detect captions region!', 'warning');
        }
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...';
    }

    try {
        let resData = null;

        if (videoPath && window.pywebview && window.pywebview.api && window.pywebview.api.detect_caption_region) {
            resData = await window.pywebview.api.detect_caption_region(videoPath);
        } else if (videoPath) {
            const res = await fetch('/api/detect_captions_region', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: videoPath })
            });
            resData = await res.json();
        } else if (videoFileObj) {
            const formData = new FormData();
            formData.append('video_file', videoFileObj);
            const res = await fetch('/api/detect_captions_region', {
                method: 'POST',
                body: formData
            });
            resData = await res.json();
        }


        if (resData && resData.detected === true && resData.posY > 0 && resData.height > 0) {
            // Real detection succeeded — apply detected values to sliders
            const setNum = (id, val) => {
                const el = document.getElementById(id);
                if (el && val !== undefined && val !== null) {
                    el.value = parseFloat(val).toFixed(2);
                    const valSpan = document.getElementById(id.replace(/^blur/, 'valBlur'));
                    if (valSpan) valSpan.textContent = parseFloat(val).toFixed(1) + '%';
                }
            };

            setNum('blurPosY', resData.posY);
            setNum('blurHeight', resData.height);
            setNum('blurPosX', resData.posX);
            setNum('blurWidth', resData.width);

            // Auto-enable Blur Box and Auto-fit toggle
            const blurToggle = document.getElementById('blurToggle');
            if (blurToggle) blurToggle.checked = true;

            const blurAutoDetectToggle = document.getElementById('blurAutoDetectToggle');
            if (blurAutoDetectToggle) blurAutoDetectToggle.checked = true;

            if (typeof updateLivePreviewOverlays === 'function') {
                updateLivePreviewOverlays();
            }

            if (typeof showToast === 'function') {
                showToast(`✨ Caption region detected! Y: ${parseFloat(resData.posY).toFixed(1)}%, Height: ${parseFloat(resData.height).toFixed(1)}%`, 'success');
            }
        } else {
            // Detection did not find a caption region — do NOT change sliders
            if (typeof showToast === 'function') {
                showToast('⚠️ Could not auto-detect captions in this video. Try adjusting the sliders manually.', 'warning');
            }
        }
    } catch (err) {
        console.warn('Caption auto-detection error:', err);
        if (typeof showToast === 'function') {
            showToast('⚠️ Caption detection error. Please check the video file and try again.', 'warning');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Auto-Detect Region';
        }
    }
}





function handleLogoSelect(input) {
    if (input && input.files && input.files[0]) {
        const file = input.files[0];
        const fileNameSpan = document.getElementById('logoFileName');
        if (fileNameSpan) fileNameSpan.textContent = file.name;
        
        const liveLogoImg = document.getElementById('liveLogoImg');
        if (liveLogoImg) {
            liveLogoImg.src = URL.createObjectURL(file);
        }
        
        const logoToggle = document.getElementById('logoToggle');
        if (logoToggle) logoToggle.checked = true;
        
        updateLivePreviewOverlays();
    }
}

async function applyVideoEdits() {
    if (!currentJobId) {
        alert('No active video job found!');
        return;
    }

    const formData = new FormData();

    // Collect all video customization settings into JSON
    const customEdits = collectCustomizationSettings();
    formData.append('custom_edits', JSON.stringify(customEdits));

    // Include RVC voice cloning params so the backend applies the selected model
    const { rvcModel, rvcPitch } = getRvcModelParams();
    formData.append('rvc_model', rvcModel);
    formData.append('rvc_pitch', rvcPitch);

    // Logo Watermark File
    const logoInput = document.getElementById('logoFileInput');
    if (logoInput && logoInput.files && logoInput.files[0]) {
        formData.append('logo_file', logoInput.files[0]);
    }

    showProgressSection('✨ Rendering Custom Video Edits...', 'render');

    try {
        const res = await fetch(`/api/render_edits/${currentJobId}`, {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (data.error) {
            alert('Video edit error: ' + data.error);
            hideProgressSection();
            return;
        }

        listenToProgress(currentJobId);
    } catch (err) {
        alert('Failed to apply video edits: ' + err.message);
        hideProgressSection();
    }
}

/* ─────────────────────────────────────────────────────────────
   Batch Video Processing System
   ───────────────────────────────────────────────────────────── */
let batchQueue = [];
let isBatchRunning = false;
let currentBatchIndex = 0;

function switchAppMode(mode) {
    const singleSection = document.getElementById('studioSection');
    const batchSection  = document.getElementById('batchSection');
    const singleBtn      = document.getElementById('modeSingleBtn');
    const batchBtn       = document.getElementById('modeBatchBtn');

    if (mode === 'batch') {
        if (singleSection) singleSection.classList.add('hidden');
        if (batchSection)  batchSection.classList.remove('hidden');
        if (singleBtn)     singleBtn.classList.remove('active');
        if (batchBtn)      batchBtn.classList.add('active');
    } else {
        if (batchSection)  batchSection.classList.add('hidden');
        if (singleSection) singleSection.classList.remove('hidden');
        if (batchBtn)      batchBtn.classList.remove('active');
        if (singleBtn)     singleBtn.classList.add('active');
    }
}

function formatDuration(seconds) {
    if (!seconds || isNaN(seconds) || seconds <= 0) return '--:--:--';
    const totalSec = Math.floor(seconds);
    const hrs = Math.floor(totalSec / 3600);
    const mins = Math.floor((totalSec % 3600) / 60);
    const secs = totalSec % 60;

    const hh = String(hrs).padStart(2, '0');
    const mm = String(mins).padStart(2, '0');
    const ss = String(secs).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
}

function loadBatchItemDuration(item) {
    if (!item) return;
    if (item.duration && item.duration !== '--:--:--') return;

    if (item.file) {
        const tempVid = document.createElement('video');
        tempVid.preload = 'metadata';
        const cleanup = function() {
            try { URL.revokeObjectURL(tempVid.src); } catch (e) {}
            tempVid.remove();
        };
        tempVid.onloadedmetadata = function() {
            if (tempVid.duration && !isNaN(tempVid.duration)) {
                item.duration = formatDuration(tempVid.duration);
                renderBatchTable();
            }
            cleanup();
        };
        tempVid.onerror = cleanup;
        tempVid.src = URL.createObjectURL(item.file);
    }

    const targetPath = item.filePath || (item.file ? item.file.path : null);
    if (targetPath) {
        // Native PyWebView API call
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_video_duration) {
            window.pywebview.api.get_video_duration(targetPath).then(dur => {
                if (dur && dur > 0) {
                    item.duration = formatDuration(dur);
                    renderBatchTable();
                }
            }).catch(e => {});
        }

        // Flask backend API call fallback
        fetch('/api/get_duration', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_path: targetPath })
        })
        .then(r => r.json())
        .then(data => {
            if (data && data.duration && data.duration > 0) {
                item.duration = formatDuration(data.duration);
                renderBatchTable();
            }
        })
        .catch(e => console.warn('Get duration error:', e));
    }
}

async function triggerBatchFilePicker() {
    // If pywebview native dialog is available, call select_batch_files API
    if (window.pywebview && window.pywebview.api && window.pywebview.api.select_batch_files) {
        try {
            const files = await window.pywebview.api.select_batch_files();
            if (files && files.length > 0) {
                // Fetch blob files for pywebview paths or add to batch queue
                for (const path of files) {
                    const fname = path.split(/[/\\]/).pop();
                    const item = {
                        id: 'batch_' + Math.random().toString(36).substr(2, 9),
                        filePath: path,
                        file: null,
                        filename: fname,
                        size: 'Local File',
                        duration: '--:--:--',
                        status: 'queued',
                        progress: 0,
                        jobId: null
                    };
                    batchQueue.push(item);
                    loadBatchItemDuration(item);
                }
                renderBatchTable();
                updateBatchBadge();
                updateStartBatchBtnState();
                return;
            }
        } catch (e) {
            console.warn('Native batch file picker error, falling back to browser input:', e);
        }
    }

    const input = document.getElementById('batchFileInput');
    if (input) input.click();
}

function handleBatchFileSelect(input) {
    if (!input || !input.files || input.files.length === 0) return;
    const files = Array.from(input.files);

    files.forEach(file => {
        const item = {
            id: 'batch_' + Math.random().toString(36).substr(2, 9),
            filePath: null,
            file: file,
            filename: file.name,
            size: formatFileSize(file.size),
            duration: '--:--:--',
            status: 'queued',
            progress: 0,
            jobId: null
        };
        batchQueue.push(item);
        loadBatchItemDuration(item);
    });

    renderBatchTable();
    updateBatchBadge();
    updateStartBatchBtnState();
    input.value = '';
}

function updateBatchBadge() {
    const badge = document.getElementById('batchCountBadge');
    if (badge) {
        if (batchQueue.length > 0) {
            badge.textContent = batchQueue.length;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }
}

function getVoiceGenderLabel(voiceId, langCode) {
    if (!voiceId || voiceId === 'auto' || voiceId === 'Auto') return 'Auto';

    const lang = langCode || (document.getElementById('targetLangSelect') ? document.getElementById('targetLangSelect').value : 'km');
    if (typeof supportedLanguages !== 'undefined' && supportedLanguages && supportedLanguages[lang] && supportedLanguages[lang].voices) {
        const found = supportedLanguages[lang].voices.find(v => v.id === voiceId);
        if (found && found.gender) {
            return found.gender === 'Female' ? 'Female' : 'Male';
        }
    }

    if (typeof supportedLanguages !== 'undefined' && supportedLanguages) {
        for (const l in supportedLanguages) {
            if (supportedLanguages[l] && supportedLanguages[l].voices) {
                const found = supportedLanguages[l].voices.find(v => v.id === voiceId);
                if (found && found.gender) {
                    return found.gender === 'Female' ? 'Female' : 'Male';
                }
            }
        }
    }

    const lower = String(voiceId).toLowerCase();
    if (lower.includes('female') || lower.includes('sreymom') || lower.includes('zira') || lower.includes('jenny') || lower.includes('aria') || lower.includes('xiaoxiao')) {
        return 'Female';
    }
    if (lower.includes('male') || lower.includes('piseth') || lower.includes('david') || lower.includes('guy') || lower.includes('yunxi')) {
        return 'Male';
    }

    return 'Auto';
}

function getBatchStatusBadgeClass(status) {
    switch (status) {
        case 'queued':     return 'badge-warning';
        case 'processing': return 'badge-info';
        case 'completed':  return 'badge-success';
        case 'failed':     return 'badge-danger';
        default:           return 'badge-secondary';
    }
}

function updateStartBatchBtnState() {
    const startBtn = document.getElementById('startBatchBtn');
    const folderBtn = document.getElementById('selectOutputFolderBtn');

    const outputFolderInput = document.getElementById('batchOutputFolderInput');
    const outputFolder = outputFolderInput ? outputFolderInput.value.trim() : '';
    const hasFolder = !!outputFolder;
    
    // Check if there are any queued (unprocessed) items in batchQueue
    const hasQueuedItems = batchQueue.some(item => item.status === 'queued');

    // Lock/unlock Output Folder button during batch processing
    if (folderBtn) {
        folderBtn.disabled = isBatchRunning;
        folderBtn.title = isBatchRunning
            ? 'Cannot change Output Folder while batch processing is running'
            : 'Select output directory where dubbed videos will auto-save';
        if (isBatchRunning) {
            folderBtn.classList.add('btn-locked');
        } else {
            folderBtn.classList.remove('btn-locked');
        }
    }

    // Lock/unlock Batch Preset dropdown during batch processing
    const presetSelect = document.getElementById('batchPresetSelect');
    const presetWrapper = document.querySelector('.batch-preset-wrapper');

    if (presetSelect) {
        presetSelect.disabled = isBatchRunning;
        presetSelect.title = isBatchRunning
            ? 'Cannot change Editing Preset while batch processing is running'
            : 'Select Editing Preset to auto-apply to all batch videos';
    }
    if (presetWrapper) {
        if (isBatchRunning) {
            presetWrapper.classList.add('btn-locked');
        } else {
            presetWrapper.classList.remove('btn-locked');
        }
    }


    if (!startBtn) return;

    if (!hasFolder) {
        startBtn.disabled = true;
        startBtn.title = 'Please select an Output Folder first before starting batch queue';
        startBtn.classList.add('btn-locked');
    } else if (!hasQueuedItems && !isBatchRunning) {
        startBtn.disabled = true;
        startBtn.title = 'Add video files to batch queue first';
        startBtn.classList.add('btn-locked');
    } else {
        // Unlock start button whenever output folder is set and queued videos exist or batch is active
        startBtn.disabled = false;
        startBtn.title = isBatchRunning ? 'Batch queue is currently processing (click for status)' : 'Start Batch Queue';
        startBtn.classList.remove('btn-locked');
    }
}

function renderBatchTable() {
    const tbody    = document.getElementById('batchTableBody');
    if (!tbody) return;

    if (batchQueue.length === 0) {
        tbody.innerHTML = `
            <tr id="emptyBatchRow">
                <td colspan="7" class="text-center py-5 text-muted">
                    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; min-height: 150px;">
                        <i class="fa-solid fa-film fa-2x" style="color: var(--primary); opacity: 0.85;"></i>
                        <p style="margin: 0; font-size: 13.5px; line-height: 1.5; color: rgba(255,255,255,0.75);">
                            Upload multiple videos and dub them sequentially with shared target voice settings.<br>
                            Click <strong>"Add Videos"</strong> to select files.
                        </p>
                    </div>
                </td>
            </tr>`;
        updateStartBatchBtnState();
        return;
    }

    updateStartBatchBtnState();

    batchQueue.forEach(item => {
        if (!item.duration || item.duration === '--:--:--') {
            loadBatchItemDuration(item);
        }
    });

    const voiceId    = document.getElementById('voiceSelect') ? document.getElementById('voiceSelect').value : 'auto';
    const targetLang = document.getElementById('targetLangSelect') ? document.getElementById('targetLangSelect').value : 'km';

    tbody.innerHTML = batchQueue.map((item, idx) => {
        const itemVoice   = item.voiceId || voiceId;
        const itemLang    = item.targetLang || targetLang;
        const genderLabel = getVoiceGenderLabel(itemVoice, itemLang);
        const genderClass = genderLabel === 'Female' ? 'gender-female' : (genderLabel === 'Male' ? 'gender-male' : 'gender-auto');
        const genderIcon  = genderLabel === 'Female' ? 'fa-venus' : (genderLabel === 'Male' ? 'fa-mars' : 'fa-robot');

        return `
        <tr id="batchRow_${item.id}">
            <td style="font-weight: 700;">${idx + 1}</td>
            <td>
                <div class="font-bold" style="font-size: 0.85rem;">${item.filename}</div>
                <div class="text-muted text-xs">${item.size}</div>
            </td>
            <td>
                <span style="font-size: 0.8rem; font-weight: 600; color: rgba(255,255,255,0.7);">
                    ${item.duration || '--:--:--'}
                </span>
            </td>
            <td>
                <span class="voice-gender-badge ${genderClass}">
                    <i class="fa-solid ${genderIcon}"></i> ${genderLabel}
                </span>
            </td>
            <td>
                <span class="badge ${getBatchStatusBadgeClass(item.status)}">
                    ${item.status.toUpperCase()}
                </span>
            </td>
            <td style="width: 180px;">
                <div class="batch-row-progress-cell">
                    <div class="progress-bar-wrapper flex-1" style="height: 6px;">
                        <div class="progress-bar" style="width: ${item.progress}%;"></div>
                    </div>
                    <span class="batch-progress-pct">${item.progress}%</span>
                </div>
            </td>
            <td>
                <button class="btn btn-xs btn-danger" onclick="removeBatchItem('${item.id}')" ${isBatchRunning ? 'disabled' : ''} title="Remove Video">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </td>
        </tr>
    `;
    }).join('');
}

function removeBatchItem(id) {
    if (isBatchRunning) return;
    batchQueue = batchQueue.filter(item => item.id !== id);
    renderBatchTable();
    updateBatchBadge();
}

function clearBatchQueue() {
    if (isBatchRunning) {
        showToast('Cannot clear queue while batch processing is active!', 'warning');
        return;
    }
    batchQueue = [];
    renderBatchTable();
    updateBatchBadge();
    const overallProgress = document.getElementById('batchOverallProgress');
    if (overallProgress) overallProgress.classList.add('hidden');
}

function updateOverallBatchProgress() {
    const total = batchQueue.length;
    if (total === 0) return;

    const completed = batchQueue.filter(i => i.status === 'completed' || i.status === 'failed').length;
    const activeProcessing = batchQueue.filter(i => i.status === 'processing');
    const activeCount = activeProcessing.length;
    const pct = Math.round((completed / total) * 100);

    const progressText = document.getElementById('batchProgressText');
    const progressBar  = document.getElementById('batchOverallProgressBar');
    const statusText   = document.getElementById('batchCurrentStatusText');

    if (progressText) progressText.textContent = `${completed} of ${total} Videos Processed (${pct}%)`;
    if (progressBar)  progressBar.style.width = pct + '%';
    if (statusText) {
        if (activeCount > 0) {
            if (activeCount === 1) {
                statusText.textContent = `Processing video: ${activeProcessing[0].filename}`;
            } else {
                statusText.textContent = `⚡ Concurrent Processing: ${activeCount} active video threads running in parallel (${completed}/${total} completed)`;
            }
        } else if (completed === total) {
            statusText.textContent = `Batch execution completed! (${completed}/${total} videos finished)`;
        } else {
            statusText.textContent = `Preparing batch queue... (${completed}/${total} completed)`;
        }
    }
}

async function browseBatchOutputFolder() {
    // Lock folder selection during batch processing
    if (isBatchRunning) {
        showToast('⚠️ Cannot change Output Folder while batch processing is running!', 'warning');
        return '';
    }

    try {
        const res = await fetch('/api/browse_folder', { method: 'POST' });
        const data = await res.json();
        if (data && data.folder) {
            const input = document.getElementById('batchOutputFolderInput');
            if (input) input.value = data.folder;
            const btnText = document.getElementById('selectOutputFolderBtnText');
            if (btnText) {
                const folderName = data.folder.split(/[/\\]/).filter(Boolean).pop() || data.folder;
                btnText.textContent = `Folder: ${folderName}`;
            }
            const btn = document.getElementById('selectOutputFolderBtn');
            if (btn) {
                btn.title = `Output Directory: ${data.folder}`;
                btn.classList.add('active-folder');
            }
            showToast(`📁 Output Directory: ${data.folder}`, 'success');
            updateStartBatchBtnState();
            return data.folder;
        }
    } catch (e) {
        console.warn('Folder browse failed:', e);
    }
    return '';
}

async function startBatchProcessing() {
    if (batchQueue.length === 0) return;

    const outputFolderInput = document.getElementById('batchOutputFolderInput');
    const outputFolder = outputFolderInput ? outputFolderInput.value.trim() : '';

    if (!outputFolder) {
        showToast('⚠️ Please select an Output Folder before starting batch processing!', 'warning');
        // Highlight the output folder button to draw attention
        const folderBtn = document.getElementById('selectOutputFolderBtn');
        if (folderBtn) {
            folderBtn.style.animation = 'none';
            folderBtn.classList.add('btn-folder-pulse');
            setTimeout(() => folderBtn.classList.remove('btn-folder-pulse'), 1800);
        }
        return;
    }

    if (isBatchRunning) {
        showToast('ℹ️ Batch queue is already processing! Newly added videos will execute automatically in sequence.', 'info');
        return;
    }

    const hasQueued = batchQueue.some(item => item.status === 'queued');
    if (!hasQueued) {
        showToast('ℹ️ All videos in the batch queue have already been processed.', 'info');
        return;
    }

    isBatchRunning = true;
    const overallProgress = document.getElementById('batchOverallProgress');
    if (overallProgress) overallProgress.classList.remove('hidden');

    renderBatchTable();
    processBatchQueuePool();
}

async function processBatchQueuePool() {
    const concurrentLimit = parseInt(localStorage.getItem('concurrent_batch_limit') || '1', 10) || 1;
    
    // Check currently processing items count
    const activeProcessing = batchQueue.filter(item => item.status === 'processing');
    const activeCount = activeProcessing.length;
    const availableSlots = concurrentLimit - activeCount;

    if (availableSlots > 0) {
        const queuedItems = batchQueue.filter(item => item.status === 'queued').slice(0, availableSlots);
        queuedItems.forEach(item => {
            processSingleBatchItem(item);
        });
    }

    // Check if batch is completely finished
    const remainingActive = batchQueue.filter(item => item.status === 'processing').length;
    const remainingQueued = batchQueue.filter(item => item.status === 'queued').length;

    if (remainingActive === 0 && remainingQueued === 0) {
        isBatchRunning = false;
        updateOverallBatchProgress();
        renderBatchTable();
        updateStartBatchBtnState();
        showToast('🎉 All batch videos processed and auto-saved successfully!', 'success');
    }
}

// Backward compatibility alias
function processNextBatchItem() {
    processBatchQueuePool();
}

async function processSingleBatchItem(item) {
    if (!item || item.status !== 'queued') return;

    item.status = 'processing';
    renderBatchTable();
    updateOverallBatchProgress();

    const targetLang = document.getElementById('targetLangSelect') ? document.getElementById('targetLangSelect').value : 'km';
    const voiceId = document.getElementById('voiceSelect') ? document.getElementById('voiceSelect').value : 'auto';
    const whisperModel = document.getElementById('whisperModelSelect') ? document.getElementById('whisperModelSelect').value : 'base';
    const vocalMode = getSelectedVocalMode();
    const subToggleEl = document.getElementById('subToggle');
    const burnSubtitles = subToggleEl ? subToggleEl.checked : false;
    const outputFolder = document.getElementById('batchOutputFolderInput') ? document.getElementById('batchOutputFolderInput').value.trim() : '';

    const formData = new FormData();
    if (item.file) {
        formData.append('video_file', item.file);
    } else if (item.filePath) {
        formData.append('file_path', item.filePath);
    }

    formData.append('target_lang', targetLang);
    formData.append('voice_id', voiceId);
    formData.append('whisper_model', whisperModel);
    formData.append('vocal_mode', vocalMode);
    formData.append('burn_subtitles', burnSubtitles);

    // Primary AI model for context analyzer & translation cascade
    const primaryAiModelBatch = localStorage.getItem('primary_ai_model') || 'gemini';
    formData.append('primary_ai_model', primaryAiModelBatch);

    if (outputFolder) {
        formData.append('output_path', outputFolder);
    }

    let customEdits = collectCustomizationSettings();
    const batchPresetSelectEl = document.getElementById('batchPresetSelect');
    const batchPresetId = batchPresetSelectEl ? batchPresetSelectEl.value : (localStorage.getItem('active_batch_preset_id') || '__none__');

    if (batchPresetId && batchPresetId !== '__none__') {
        const globalPresets = getGlobalPresets();
        const foundPreset = globalPresets.find(p => p.id === batchPresetId);
        if (foundPreset && foundPreset.settings) {
            customEdits = foundPreset.settings;
        }
    }

    formData.append('custom_edits', JSON.stringify(customEdits));


    try {
        const res = await fetch('/api/process_file', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.job_id) {
            item.jobId = data.job_id;
            listenToBatchProgress(item, data.job_id);
        } else {
            item.status = 'failed';
            renderBatchTable();
            updateOverallBatchProgress();
            processBatchQueuePool();
        }
    } catch (err) {
        item.status = 'failed';
        renderBatchTable();
        updateOverallBatchProgress();
        processBatchQueuePool();
    }
}

function listenToBatchProgress(item, jobId) {
    const es = new EventSource(`/api/progress/${jobId}`);
    es.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            item.progress = data.progress || 0;
            if (data.video_duration && data.video_duration > 0) {
                item.duration = formatDuration(data.video_duration);
            } else if (data.result_data && data.result_data.video_duration) {
                item.duration = formatDuration(data.result_data.video_duration);
            }
            renderBatchTable();
            updateOverallBatchProgress();

            if (data.status === 'completed') {
                es.close();
                item.status = 'completed';
                item.progress = 100;
                renderBatchTable();
                updateOverallBatchProgress();
                processBatchQueuePool();
            } else if (data.status === 'failed') {
                es.close();
                item.status = 'failed';
                renderBatchTable();
                updateOverallBatchProgress();
                processBatchQueuePool();
            }
        } catch (e) {}
    };
    es.onerror = () => {
        es.close();
        item.status = 'failed';
        renderBatchTable();
        updateOverallBatchProgress();
        processBatchQueuePool();
    };
}

async function downloadBatchOutput(jobId, fileType) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file) {
        try {
            const res = await window.pywebview.api.save_file(jobId, fileType);
            if (res && res.ok) {
                alert(`File saved successfully to: ${res.path}`);
                return;
            } else if (res && res.error !== 'Cancelled') {
                alert(`Save failed: ${res.error}`);
                return;
            }
        } catch (e) {
            console.warn('Native save dialog error, falling back to direct download:', e);
        }
    }
    window.location.href = `/api/download/${jobId}/${fileType}`;
}

function triggerLogoBrowse() {
    const fileInput = document.getElementById('logoFileInput');
    if (fileInput) fileInput.click();
}

function clearLogoFile() {
    const fileInput = document.getElementById('logoFileInput');
    const nameEl = document.getElementById('logoFileName');
    if (fileInput) fileInput.value = '';
    if (nameEl) nameEl.textContent = 'No logo selected';
    const logoToggle = document.getElementById('logoToggle');
    if (logoToggle) logoToggle.checked = false;
    updateLivePreviewOverlays();
}

function triggerPipBrowse() {
    const fileInput = document.getElementById('pipFileInput');
    if (fileInput) fileInput.click();
}

function handlePipFileSelect(input) {
    const nameEl = document.getElementById('pipFileName');
    if (input.files && input.files[0]) {
        if (nameEl) nameEl.textContent = input.files[0].name;
        const pipToggle = document.getElementById('pipToggle');
        if (pipToggle) pipToggle.checked = true;
    } else {
        if (nameEl) nameEl.textContent = 'No PIP video selected';
    }
    updateLivePreviewOverlays();
}

function clearPipFile() {
    const fileInput = document.getElementById('pipFileInput');
    const nameEl = document.getElementById('pipFileName');
    if (fileInput) fileInput.value = '';
    if (nameEl) nameEl.textContent = 'No PIP video selected';
    const pipToggle = document.getElementById('pipToggle');
    if (pipToggle) pipToggle.checked = false;
    updateLivePreviewOverlays();
}

function toggleSubStyle(styleType) {
    const btn = document.getElementById(styleType === 'bold' ? 'subBoldBtn' : 'subItalicBtn');
    if (btn) btn.classList.toggle('active');
    updateLivePreviewOverlays();
}

function toggleTextStyle(styleType) {
    const btn = document.getElementById(styleType === 'bold' ? 'textBoldBtn' : 'textItalicBtn');
    if (btn) btn.classList.toggle('active');
    updateLivePreviewOverlays();
}
