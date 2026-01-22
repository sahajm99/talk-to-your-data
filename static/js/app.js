// ============================================
// Configuration & State
// ============================================

const CONFIG = {
    API_BASE_URL: window.location.origin,
    DEFAULT_PROJECT_ID: 'test',
    DEFAULT_TOP_K: 5,
    MAX_MESSAGE_LENGTH: 2000,
};

const state = {
    sessionId: null,
    projectId: CONFIG.DEFAULT_PROJECT_ID,
    topK: CONFIG.DEFAULT_TOP_K,
    includeImages: true,
    isProcessing: false,
    messages: [],
};

// ============================================
// DOM Elements
// ============================================

const elements = {
    // Sidebar
    projectInput: document.getElementById('projectInput'),
    fileInput: document.getElementById('fileInput'),
    uploadArea: document.getElementById('uploadArea'),
    uploadStatus: document.getElementById('uploadStatus'),
    sessionStatus: document.getElementById('sessionStatus'),
    sessionId: document.getElementById('sessionId'),
    clearSessionBtn: document.getElementById('clearSessionBtn'),
    topKInput: document.getElementById('topKInput'),
    includeImagesCheck: document.getElementById('includeImagesCheck'),
    toggleSidebarBtn: document.getElementById('toggleSidebarBtn'),

    // Main content
    messagesContainer: document.getElementById('messagesContainer'),
    queryInput: document.getElementById('queryInput'),
    sendBtn: document.getElementById('sendBtn'),

    // Overlays
    loadingOverlay: document.getElementById('loadingOverlay'),
    toastContainer: document.getElementById('toastContainer'),
    imageModal: document.getElementById('imageModal'),
    modalImage: document.getElementById('modalImage'),
    modalCaption: document.getElementById('modalCaption'),
    modalCloseBtn: document.getElementById('modalCloseBtn'),
};

// ============================================
// Initialization
// ============================================

function init() {
    setupEventListeners();
    loadSettings();
    updateSessionDisplay();

    console.log('App initialized');
}

function setupEventListeners() {
    // Project input
    elements.projectInput.addEventListener('change', (e) => {
        state.projectId = e.target.value.trim() || CONFIG.DEFAULT_PROJECT_ID;
        saveSettings();
    });

    // Settings
    elements.topKInput.addEventListener('change', (e) => {
        state.topK = parseInt(e.target.value) || CONFIG.DEFAULT_TOP_K;
        saveSettings();
    });

    elements.includeImagesCheck.addEventListener('change', (e) => {
        state.includeImages = e.target.checked;
        saveSettings();
    });

    // Upload
    elements.uploadArea.addEventListener('click', () => {
        elements.fileInput.click();
    });

    elements.fileInput.addEventListener('change', handleFileUpload);

    // Drag and drop
    elements.uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.uploadArea.classList.add('dragover');
    });

    elements.uploadArea.addEventListener('dragleave', () => {
        elements.uploadArea.classList.remove('dragover');
    });

    elements.uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFiles(files);
        }
    });

    // Session
    elements.clearSessionBtn.addEventListener('click', clearSession);

    // Chat input
    elements.queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuery();
        }
    });

    elements.queryInput.addEventListener('input', autoResizeTextarea);

    elements.sendBtn.addEventListener('click', sendQuery);

    // Example questions
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('example-btn')) {
            const query = e.target.dataset.query;
            elements.queryInput.value = query;
            sendQuery();
        }
    });

    // Sidebar toggle
    elements.toggleSidebarBtn.addEventListener('click', () => {
        document.querySelector('.sidebar').classList.toggle('collapsed');
    });

    // Modal
    elements.modalCloseBtn.addEventListener('click', closeModal);
    elements.imageModal.addEventListener('click', (e) => {
        if (e.target === elements.imageModal) {
            closeModal();
        }
    });
}

// ============================================
// Settings Persistence
// ============================================

function saveSettings() {
    localStorage.setItem('chatAppSettings', JSON.stringify({
        projectId: state.projectId,
        topK: state.topK,
        includeImages: state.includeImages,
    }));
}

function loadSettings() {
    const saved = localStorage.getItem('chatAppSettings');
    if (saved) {
        try {
            const settings = JSON.parse(saved);
            state.projectId = settings.projectId || CONFIG.DEFAULT_PROJECT_ID;
            state.topK = settings.topK || CONFIG.DEFAULT_TOP_K;
            state.includeImages = settings.includeImages !== false;

            elements.projectInput.value = state.projectId;
            elements.topKInput.value = state.topK;
            elements.includeImagesCheck.checked = state.includeImages;
        } catch (e) {
            console.error('Failed to load settings:', e);
        }
    }
}

// ============================================
// File Upload
// ============================================

async function handleFileUpload(e) {
    const files = e.target.files;
    if (files.length > 0) {
        await uploadFiles(files);
    }
    e.target.value = ''; // Reset input
}

async function uploadFiles(files) {
    if (files.length === 0) return;

    const formData = new FormData();
    formData.append('project_id', state.projectId);

    for (let file of files) {
        formData.append('files', file);
    }

    elements.uploadStatus.innerHTML = `
        <div class="upload-progress">
            <div>Uploading ${files.length} file(s)...</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: 0%"></div>
            </div>
        </div>
    `;

    try {
        const response = await fetch(`${CONFIG.API_BASE_URL}/ingest/files`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }

        const result = await response.json();

        // Show success message
        const totalChunks = result.summary.reduce((sum, file) =>
            sum + (file.num_chunks || 0), 0
        );

        elements.uploadStatus.innerHTML = `
            <div style="color: var(--success-color); font-weight: 600;">
                ✓ Uploaded successfully!<br>
                ${files.length} file(s), ${totalChunks} chunks created
            </div>
        `;

        showToast('success', `Successfully uploaded ${files.length} file(s)`);

        // Clear after 5 seconds
        setTimeout(() => {
            elements.uploadStatus.innerHTML = '';
        }, 5000);

    } catch (error) {
        console.error('Upload error:', error);
        elements.uploadStatus.innerHTML = `
            <div style="color: var(--error-color);">
                ✗ Upload failed: ${error.message}
            </div>
        `;
        showToast('error', `Upload failed: ${error.message}`);
    }
}

// ============================================
// Chat Functions
// ============================================

async function sendQuery() {
    const query = elements.queryInput.value.trim();

    if (!query || state.isProcessing) return;

    if (query.length > CONFIG.MAX_MESSAGE_LENGTH) {
        showToast('error', `Message too long (max ${CONFIG.MAX_MESSAGE_LENGTH} characters)`);
        return;
    }

    // Clear input and welcome message
    elements.queryInput.value = '';
    autoResizeTextarea();
    clearWelcomeMessage();

    // Add user message to UI
    addMessage('user', query);

    // Show typing indicator
    const typingId = showTypingIndicator();

    state.isProcessing = true;
    elements.sendBtn.disabled = true;

    try {
        const requestBody = {
            project_id: state.projectId,
            query: query,
            top_k: state.topK,
            include_images: state.includeImages,
        };

        if (state.sessionId) {
            requestBody.session_id = state.sessionId;
        }

        const response = await fetch(`${CONFIG.API_BASE_URL}/chat/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
        });

        removeTypingIndicator(typingId);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Query failed');
        }

        const result = await response.json();

        // Update session
        state.sessionId = result.session_id;
        updateSessionDisplay();

        // Add assistant message
        addMessage('assistant', result.answer, result.sources, {
            retrieval_time_ms: result.retrieval_time_ms,
            generation_time_ms: result.generation_time_ms,
            total_time_ms: result.total_time_ms,
        });

    } catch (error) {
        console.error('Query error:', error);
        removeTypingIndicator(typingId);
        addMessage('assistant', `Sorry, I encountered an error: ${error.message}`);
        showToast('error', `Query failed: ${error.message}`);
    } finally {
        state.isProcessing = false;
        elements.sendBtn.disabled = false;
        elements.queryInput.focus();
    }
}

function addMessage(role, content, sources = null, metrics = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const timestamp = new Date().toLocaleTimeString();

    let html = `
        <div class="message-header">
            <div class="message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
            <div class="message-role">${role}</div>
            <div class="message-time">${timestamp}</div>
        </div>
        <div class="message-bubble">
            <div class="message-content">${escapeHtml(content)}</div>
    `;

    // Add sources if available
    if (sources && sources.length > 0) {
        html += renderSources(sources);
    }

    // Add metrics if available
    if (metrics) {
        html += renderMetrics(metrics);
    }

    html += `</div>`;

    messageDiv.innerHTML = html;
    elements.messagesContainer.appendChild(messageDiv);
    scrollToBottom();

    // Store message
    state.messages.push({ role, content, sources, metrics, timestamp });
}

function renderSources(sources) {
    let html = `
        <div class="sources-section">
            <div class="sources-header">
                <span class="sources-icon">📚</span>
                <span class="sources-title">Sources</span>
                <span class="sources-count">${sources.length}</span>
            </div>
    `;

    sources.forEach((source, index) => {
        const pageInfo = source.page_number ? `Page ${source.page_number}` : 'No page';
        const scorePercent = (source.score * 100).toFixed(1);

        html += `
            <div class="source-item" data-source-index="${index}">
                <div class="source-header">
                    <div class="source-title">
                        [${index + 1}] ${escapeHtml(source.file_name)}
                    </div>
                    <div class="source-score">${scorePercent}%</div>
                </div>
                <div class="source-meta">
                    ${pageInfo} • ${source.chunk_type || 'text'} • Chunk ${source.chunk_index}
                </div>
                <div class="source-text">${escapeHtml(source.text)}</div>
        `;

        // Add image if available
        if (source.image_path && state.includeImages) {
            const imagePath = `${CONFIG.API_BASE_URL}${source.image_path}`;
            html += `
                <div class="source-image" onclick="openImageModal('${imagePath}', '${escapeHtml(source.file_name)} - Page ${source.page_number}')">
                    <img src="${imagePath}" alt="Source chunk image" loading="lazy">
                </div>
            `;
        }

        html += `</div>`;
    });

    html += `</div>`;
    return html;
}

function renderMetrics(metrics) {
    return `
        <div class="metrics">
            <div class="metric">
                <span class="metric-icon">🔍</span>
                <span>Retrieval: ${metrics.retrieval_time_ms.toFixed(0)}ms</span>
            </div>
            <div class="metric">
                <span class="metric-icon">💬</span>
                <span>Generation: ${metrics.generation_time_ms.toFixed(0)}ms</span>
            </div>
            <div class="metric">
                <span class="metric-icon">⏱️</span>
                <span>Total: ${metrics.total_time_ms.toFixed(0)}ms</span>
            </div>
        </div>
    `;
}

function showTypingIndicator() {
    const id = `typing-${Date.now()}`;
    const div = document.createElement('div');
    div.id = id;
    div.className = 'message assistant';
    div.innerHTML = `
        <div class="message-header">
            <div class="message-avatar">🤖</div>
            <div class="message-role">Assistant</div>
        </div>
        <div class="message-bubble">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    elements.messagesContainer.appendChild(div);
    scrollToBottom();
    return id;
}

function removeTypingIndicator(id) {
    const element = document.getElementById(id);
    if (element) {
        element.remove();
    }
}

function clearWelcomeMessage() {
    const welcome = elements.messagesContainer.querySelector('.welcome-message');
    if (welcome) {
        welcome.remove();
    }
}

// ============================================
// Session Management
// ============================================

async function clearSession() {
    if (!state.sessionId) {
        showToast('info', 'No active session to clear');
        return;
    }

    if (!confirm('Clear conversation history?')) {
        return;
    }

    try {
        const response = await fetch(
            `${CONFIG.API_BASE_URL}/chat/history/${state.sessionId}`,
            { method: 'DELETE' }
        );

        if (!response.ok) {
            throw new Error('Failed to clear session');
        }

        // Reset state
        state.sessionId = null;
        state.messages = [];

        // Clear UI
        elements.messagesContainer.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">💬</div>
                <h3>Conversation Cleared!</h3>
                <p>Start a new conversation by asking a question.</p>
            </div>
        `;

        updateSessionDisplay();
        showToast('success', 'Conversation history cleared');

    } catch (error) {
        console.error('Clear session error:', error);
        showToast('error', `Failed to clear session: ${error.message}`);
    }
}

function updateSessionDisplay() {
    if (state.sessionId) {
        elements.sessionStatus.textContent = 'Active';
        elements.sessionStatus.style.color = 'var(--success-color)';
        elements.sessionId.textContent = state.sessionId.substring(0, 8) + '...';
    } else {
        elements.sessionStatus.textContent = 'New Session';
        elements.sessionStatus.style.color = 'var(--text-tertiary)';
        elements.sessionId.textContent = '-';
    }
}

// ============================================
// UI Utilities
// ============================================

function autoResizeTextarea() {
    const textarea = elements.queryInput;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

function scrollToBottom() {
    elements.messagesContainer.scrollTop = elements.messagesContainer.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// Toast Notifications
// ============================================

function showToast(type, message, duration = 5000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '✓',
        error: '✗',
        info: 'ℹ',
        warning: '⚠',
    };

    toast.innerHTML = `
        <div class="toast-icon">${icons[type] || 'ℹ'}</div>
        <div class="toast-message">${escapeHtml(message)}</div>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    elements.toastContainer.appendChild(toast);

    // Auto remove after duration
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ============================================
// Image Modal
// ============================================

function openImageModal(imagePath, caption) {
    elements.modalImage.src = imagePath;
    elements.modalCaption.textContent = caption;
    elements.imageModal.style.display = 'flex';
}

function closeModal() {
    elements.imageModal.style.display = 'none';
    elements.modalImage.src = '';
}

// Make function global for onclick
window.openImageModal = openImageModal;

// ============================================
// Loading Overlay
// ============================================

function showLoading(text = 'Processing...') {
    elements.loadingOverlay.querySelector('.loading-text').textContent = text;
    elements.loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    elements.loadingOverlay.style.display = 'none';
}

// ============================================
// Initialize on DOM Ready
// ============================================

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
