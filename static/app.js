function acceptDisclaimer() {
    document.querySelector('.disclaimer').style.display = 'none';
    document.querySelector('.chat-container').style.display = 'block';
    document.querySelector('.file-upload').style.display = 'block';
    document.querySelector('.input-group').style.display = 'flex';
}

function declineDisclaimer() {
    alert('You must accept the disclaimer to use OpenProBono AI.');
}

let uploadedFiles = [];

function handleFileUpload(files) {
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = '';

    for (let i = 0; i < files.length && uploadedFiles.length < 5; i++) {
        const file = files[i];
        if (file.size <= 5 * 1024 * 1024) { // 5MB in bytes
            uploadedFiles.push(file);
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span>${file.name}</span>
                <button class="btn btn-sm btn-danger" onclick="removeFile(${uploadedFiles.length - 1})">Remove</button>
            `;
            fileList.appendChild(fileItem);
        } else {
            alert(`File ${file.name} is larger than 5MB and won't be uploaded.`);
        }
    }

    if (files.length > 5) {
        alert('Maximum of 5 files allowed. Only the first 5 files have been added.');
    }

    document.getElementById('file-input').value = '';
}

function removeFile(index) {
    uploadedFiles.splice(index, 1);
    updateFileList();
}

function updateFileList() {
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = '';
    uploadedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span>${file.name}</span>
            <button class="btn btn-sm btn-danger" onclick="removeFile(${index})">Remove</button>
        `;
        fileList.appendChild(fileItem);
    });
}

function getFileIcon(fileName) {
    const extension = fileName.split('.').pop().toLowerCase();
    switch (extension) {
        case 'txt': return 'bi-file-text';
        case 'doc':
        case 'docx': return 'bi-file-word';
        case 'pdf': return 'bi-file-pdf';
        default: return 'bi-file-earmark';
    }
}

let feedbackAction = '';
function setFeedbackAction(element) {
    feedbackAction = element.title;
    console.log(feedbackAction);
}

function formatDate(dateString) {
    const [year, month, day] = dateString.split('-');
    const months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];
    return `${months[parseInt(month) - 1]} ${parseInt(day)}, ${year}`;
}

function longestCommonSubstring(str1, str2) {
    const m = Array(str1.length + 1).fill().map(() => Array(str2.length + 1).fill(0));
    let longest = 0;
    for (let x = 1; x <= str1.length; x++) {
        for (let y = 1; y <= str2.length; y++) {
            if (str1[x - 1] === str2[y - 1]) {
                m[x][y] = m[x - 1][y - 1] + 1;
                longest = Math.max(longest, m[x][y]);
            }
        }
    }
    return longest;
}

function buildCitationMap(msg) {
    console.log(msg);
}

let eventSource;
let currentSessionId = null;
async function sendMessage() {
    const userInput = document.getElementById('user-input');
    if (userInput.value.trim() === '' && uploadedFiles.length === 0) return;

    // Add user message
    addMessageToChat('user', userInput.value);

    // Clear input and file list
    const userMessage = userInput.value;
    const userFiles = uploadedFiles;
    userInput.value = '';
    uploadedFiles = [];
    updateFileList();

    if (eventSource) {
        eventSource.close();
    }

    try {
        if (!currentSessionId) {
            await getNewSession();
        }
        // Only use FormData if we have files
        if (userFiles.length > 0) {
            const formData = new FormData();
            formData.append('sessionId', currentSessionId);
            userFiles.forEach((file) => {
                formData.append('files', file);
            });

            const response = await fetch('/chat', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) throw new Error('Failed to upload files');
        }
        // Prepare stream args
        const params = new URLSearchParams({
            sessionId: currentSessionId,
            message: userMessage
        });
        eventSource = new EventSource(`/chat?${params}`);
        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            handleStreamEvent(data);
        };
        eventSource.onerror = function(error) {
            console.error('EventSource failed:', error);
            eventSource.close();
            addMessageToChat('error', 'An error occurred while streaming the response.');
        };
    } catch (error) {
        console.error('Error: ', error);
        addMessageToChat('error', 'An error occurred while sending your message.');
    }
}

let botMessageContainer = null;
let rawBotMessageContent = '';
async function handleStreamEvent(data) {
    switch(data.type) {
        case 'tool_call':
            let toolContent = `<h5>Tool Call</h5>
            <p><strong>Name:</strong> ${data.name}</p>
            <p><strong>Arguments:</strong> ${data.args}</p>
            <p><i>The tool is gathering sources<span id="${data.id}-dots" class="dots"></span></i></p>`;
            addMessageToChat('tool', toolContent);
            break;
        case 'tool_result':
            updateSources(data.results);
            let toolDots = document.getElementById(`${data.id}-dots`);
            toolDots.classList.remove('dots');
            toolDots.innerHTML = '...finished.';
            break;
        case 'response':
            if (!botMessageContainer) {
                // It's the beginning of a bot message
                // Create bot message container
                botMessageContainer = document.createElement('div');
                botMessageContainer.className = 'message bot-message-container';
                botMessageContainer.innerHTML = '<div class="bot-message"></div>';
                addMessageIcons(botMessageContainer);
                // Append it to the chatbox
                const chatMessages = document.getElementById('chat-messages');
                chatMessages.appendChild(botMessageContainer);
                rawBotMessageContent = '';
            }
            let content = data.content;
            rawBotMessageContent += data.content;
            const html = marked.parse(content);
            let tempContainer = document.createElement('div');
            tempContainer.innerHTML = html;

            // Add fade-in class to each new element
            tempContainer.querySelectorAll('p, ul li, ol li').forEach(el => {
                el.classList.add('bot-message-stream');
            });

            let botMessageElement = botMessageContainer.querySelector('.bot-message');
            botMessageElement.appendChild(tempContainer);
            break;
        case 'done':
            if (eventSource) {
                eventSource.close();
                buildCitationMap(rawBotMessageContent);
            }
            botMessageContainer = null;
            let sessions = loadSavedSessions();
            // If it's a new session, get the title/timestamp and add it to local storage
            if (!sessions.find(session => session.id == currentSessionId))
                await saveCurrentSession();
            break;
        default:
            console.warn('Unknown event type:', data.type);
    }

    // Scroll to bottom
    if (botMessageContainer)
        botMessageContainer.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function addMessageToChat(type, content) {
    const chatMessages = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message';            
    if (uploadedFiles.length > 0) {
        content += '<div class="file-thumbnails">';
        uploadedFiles.forEach(file => {
            const icon = getFileIcon(file.name);
            content += `
                <div class="file-thumbnail">
                    <i class="bi ${icon}"></i>
                    <span>${file.name}</span>
                </div>
            `;
        });
        content += '</div>';
    }
    messageDiv.innerHTML = `<div class="${type}-message">${content}</div>`;
    chatMessages.appendChild(messageDiv);
    messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function addMessageIcons(container) {
    const iconsDiv = document.createElement('div');
    iconsDiv.className = 'message-icons';
    iconsDiv.innerHTML = `
        <i class="bi bi-hand-thumbs-up icon" data-bs-toggle="modal" data-bs-target="#likeModal" onclick="setFeedbackAction(this)" title="Like"></i>
        <i class="bi bi-hand-thumbs-down icon" data-bs-toggle="modal" data-bs-target="#dislikeModal" onclick="setFeedbackAction(this)" title="Dislike"></i>
    `;
    container.appendChild(iconsDiv);
}

function generateSourceHTML(source, index, entities) {
    let html = '';
    let url = '';
    let aiSummary = '';
    let entitiesHTML = '';
    switch (source.type) {
        case 'opinion':
            url = `https://www.courtlistener.com/opinion/${source.entity.metadata.cluster_id}/${source.entity.metadata.slug}`;
            let authorAndDates = 'Unknown Author';
            if (Object.hasOwn(source.entity.metadata, 'author_name')) {
                authorAndDates = source.entity.metadata.author_name;
            }
            authorAndDates += ' | ' + formatDate(source.entity.metadata.date_filed);
            if (Object.hasOwn(source.entity.metadata, 'date_blocked')) {
                authorAndDates += ' | Blocked ' + formatDate(source.entity.metadata.date_blocked);
            }
            let downloadUrl = '';
            if (Object.hasOwn(source.entity.metadata, 'download_url')) {
                downloadUrl = `<p class="card-text"><strong>Download Link</strong>: <a href="${source.entity.metadata.download_url}">${source.entity.metadata.download_url}</a></p>`;
            }
            let summary = '';
            if (Object.hasOwn(source.entity.metadata, 'summary')) {
                summary = `<p class="card-text"><strong>CourtListener Summary</strong>:</p><div class="ms-2">${source.entity.metadata.summary}</div>`;
            }
            aiSummary = '';
            if (Object.hasOwn(source.entity.metadata, 'ai_summary')) {
                mrkdwnSummary = marked.parse(source.entity.metadata.ai_summary);
                aiSummary = `<p class="card-text"><strong>AI Summary</strong>:</p><div class="ms-2">${mrkdwnSummary}</div>`;
            }
            let otherDates = '';
            if (Object.hasOwn(source.entity.metadata, 'other_dates')) {
                otherDates = `<p class="card-text"><strong>Other dates</strong>: ${source.entity.metadata.other_dates}</p>`;
            }
            // Modify the excerpt part to include multiple excerpts
            entitiesHTML = `
                <div class="mt-2">
                    <p class="card-text"><strong>Excerpt${entities.length > 1 ? 's' : ''} (${entities.length})</strong>:</p>
                    <ol class="list-group">
            `;
            entitiesHTML += entities.map(entity => `
                <li class="list-group-item">
                    <div class="p-2" style="border: 2px solid #737373; background-color:#F0F0F0; overflow-y: scroll; max-height: 500px;">${entity.text}</div>
                </li>
            `).join('');
            entitiesHTML += '</ol></div>';
            html = `
                <div class="card-header d-flex justify-content-between align-items-center" id="collapseTrigger${index + 1}" style="cursor:pointer;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="25" height="25" fill="currentColor" class="bi bi-briefcase-fill" viewBox="0 0 25 25">
                        <path d="M6.5 1A1.5 1.5 0 0 0 5 2.5V3H1.5A1.5 1.5 0 0 0 0 4.5v1.384l7.614 2.03a1.5 1.5 0 0 0 .772 0L16 5.884V4.5A1.5 1.5 0 0 0 14.5 3H11v-.5A1.5 1.5 0 0 0 9.5 1zm0 1h3a.5.5 0 0 1 .5.5V3H6v-.5a.5.5 0 0 1 .5-.5"/>
                        <path d="M0 12.5A1.5 1.5 0 0 0 1.5 14h13a1.5 1.5 0 0 0 1.5-1.5V6.85L8.129 8.947a.5.5 0 0 1-.258 0L0 6.85z"/>
                    </svg>
                    <div style="flex: 1; margin: 0 15px;">
                        <h5>${index + 1}. ${source.entity.metadata.case_name}</h5>
                    </div>
                    <i id="collapseIcon${index + 1}" class="bi bi-chevron-up"></i>
                </div>
                <div id="collapseContent${index + 1}" style="display:none;">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2">${source.entity.metadata.court_name}</h6>
                        <h6 class="card-subtitle mb-2 text-muted">${authorAndDates}</h6>
                        <p class="card-text"><strong>CourtListener Link</strong>: <a href="${url}">${url}</a></p>
                        ${downloadUrl}
                        ${summary}
                        ${aiSummary}
                        ${otherDates}
                        ${entitiesHTML}
                    </div>
                </div>
            `;
            break;
        case 'url':
            url = source.id;
            let urlSource = 'Unknown Source';
            if (Object.hasOwn(source.entity.metadata, 'source')) {
                urlSource = source.entity.metadata.source;
            }
            let urlTitle = 'Unknown Title';
            if (Object.hasOwn(source.entity.metadata, 'title')) {
                urlTitle = source.entity.metadata.title;
            }
            let favicon = '';
            if (Object.hasOwn(source.entity.metadata, 'favicon')) {
                favicon = `<img src="${source.entity.metadata.favicon}" alt="${urlSource} favicon" style="width: 25px; height: 25px;">`;
            } else {
                favicon = `<div style="width:25px; min-width: 25px;"></div>`;
            }
            aiSummary = '';
            if (Object.hasOwn(source.entity.metadata, 'ai_summary')) {
                mrkdwnSummary = marked.parse(source.entity.metadata.ai_summary);
                aiSummary = `<p class="card-text"><strong>AI Summary</strong>:</p><div class="ms-2">${mrkdwnSummary}</div>`;
            }
            entitiesHTML = `
                <div class="mt-2">
                    <p class="card-text"><strong>Excerpt${entities.length > 1 ? 's' : ''} (${entities.length})</strong>:</p>
                    <ol class="list-group">
            `;
            entitiesHTML += entities.map(entity => `
                <li class="list-group-item">
                    <div class="p-2" style="border: 2px solid #737373; background-color:#F0F0F0; overflow-y: scroll; max-height: 500px;">${entity.text}</div>
                </li>
            `).join('');
            entitiesHTML += '</ol></div>';
            html = `
                <div class="card-header d-flex justify-content-between align-items-center" id="collapseTrigger${index + 1}" style="cursor:pointer;">
                    ${favicon}
                    <div style="flex: 1; margin: 0 15px;">
                        <h5>${index + 1}. ${urlSource}</h5>
                        <h6 class="card-subtitle mb-0">${urlTitle}</h6>
                    </div>
                    <i id="collapseIcon${index + 1}" class="bi bi-chevron-up"></i>
                </div>
                <div id="collapseContent${index + 1}" style="display:none;">
                    <div class="card-body">
                        <p class="card-text"><strong>Link</strong>: <a href="${url}">${url}</a></p>
                        ${aiSummary}
                        ${entitiesHTML}
                    </div>
                </div>
            `;
            break;
        case 'file':
            // Modify the excerpt part to include multiple excerpts
            entitiesHTML = entities.map(entity => `<p class="card-text">${entity.text}</p>`).join('');
            html = `
                <div class="card-body">
                    <h5 class="card-title">${index + 1}. ${source.id}</h5>
                    ${entitiesHTML}
                </div>
            `;
            break;
        case 'unknown':
            console.warn('Unknown source: ', source);
            html = `
                <div class="card-body">
                    <h5 class="card-title">${index + 1}. ${source.id}</h5>
                    <p class="card-text">Unknown entity. Text unavailable.</p>
                </div>
            `;
            break;
        default:
            console.error('Unexpected source: ', source);
            html = `
                <div class="card-body">
                    <h5 class="card-title">${index + 1}. ${source}</h5>
                    <p class="card-text">Unexpected entity. Text unavailable.</p>
                </div>
            `;
    }
    return html;
}

let sourceMap = new Map(); // To keep track of sources and their excerpts
function updateSources(newSources) {
    const sourceList = document.getElementById('source-list');
    sourceList.innerHTML = ''; // Clear previous sources
    newSources.forEach((source, i) => {
        if (sourceMap.has(source.id)) {
            let existingEntities = sourceMap.get(source.id).entities;
            // Check for duplicate using the entity's unique id
            if (!existingEntities.some(entity => entity.pk === source.entity.pk)) {
                existingEntities.push(source.entity); // Store the full entity
            }
        } else {
            // If it's a new source, add it to the map
            sourceMap.set(source.id, {
                source: source,
                entities: [source.entity],
                originalIndex: sourceMap.size // To maintain original order
            });
        }
    });

    // Sort the sources based on their original index
    const sortedSources = Array.from(sourceMap.values()).sort((a, b) => a.originalIndex - b.originalIndex);
    sortedSources.forEach((sourceData, i) => {
        // Sort the entities by primary key
        sourceData.entities.sort((a, b) => a.pk.localeCompare(b.pk));
        const sourceItem = document.createElement('div');
        sourceItem.className = 'card mb-3';
        sourceItem.innerHTML = generateSourceHTML(sourceData.source, i, sourceData.entities);
        // Make source cards collapsible
        sourceItem.querySelector('#collapseTrigger' + (i + 1)).addEventListener('click', () => {
            const collapseIcon = sourceItem.querySelector('#collapseIcon' + (i + 1));
            if (collapseIcon.classList.contains('bi-chevron-down')) {
                // Collapse the content
                collapseIcon.classList.replace('bi-chevron-down', 'bi-chevron-up');
                sourceItem.querySelector('#collapseContent' + (i + 1)).style.display = 'none';
            } else {
                // Expand the content
                collapseIcon.classList.replace('bi-chevron-up', 'bi-chevron-down');
                sourceItem.querySelector('#collapseContent' + (i + 1)).style.display = '';
            }
        });
        sourceList.appendChild(sourceItem);
    });
}

async function getNewSession() {
    try {
        const response = await fetch('/new_session', { method: 'POST' });
        if (response.ok) {
            const data = await response.json();
            currentSessionId = data.session_id;
            // Update URL without reloading page
            window.history.pushState({}, '', `?session=${currentSessionId}`);
        }
    } catch (error) {
        console.error('Failed to create new session:', error);
    }
}

function clearSessionMessages() {
    // Clear current chat
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.innerHTML = '';
    // Clear current source list mapping
    sourceMap.clear();
    // Clear current source list HTML
    const sourceList = document.getElementById('source-list');
    sourceList.innerHTML = '';
}

async function switchSession(sessionId) {
    clearSessionMessages();

    try {
        const response = await fetch(`/get_session_messages/${sessionId}`);
        if (response.ok) {
            const messages = await response.json();
            messages.history.forEach(msg => {
                if (msg.type === "user")
                    addMessageToChat(msg.type, msg.content);
                else {
                    handleStreamEvent(msg);
                    // No done event in loaded messages so reset the container
                    botMessageContainer = null;
                }
            });
            currentSessionId = sessionId;
            // Update URL without reloading page
            window.history.pushState({}, '', `?session=${sessionId}`);
        }
    } catch (error) {
        console.error('Failed to load session messages:', error);
        addMessageToChat('error', 'Failed to load conversation history');
    }
}

function clearSession() {
    clearSessionMessages();
    // Clear old session from URL
    window.history.pushState({}, '', window.location.pathname);
    // Clear session ID variable
    currentSessionId = null;
}

async function saveCurrentSession() {
    const response = await fetch(`/sessions?ids[]=${currentSessionId}`);
    if (!response.ok) throw new Error('Failed to get sessions from server');
    let fetchedSessions = await response.json();
    let savedSessions = loadSavedSessions();
    let newSessions = savedSessions.concat(fetchedSessions);
    saveSessions(newSessions);
    addSessionToSidebar(fetchedSessions[0]);
}

function loadSavedSessions() {
    return JSON.parse(localStorage.getItem('sessions') || '[]');
}

function saveSessions(sessions) {
    localStorage.setItem('sessions', JSON.stringify(sessions));
}

function displaySessionsSidebar() {
    const sessions = loadSavedSessions();
    const sessionsList = document.getElementById('sessionsList');
    sessionsList.innerHTML = '';
    
    // Group sessions by date
    const grouped = {
        last_week: [],
        last_month: [],
        older: []
    };
    
    const now = new Date();
    sessions.forEach(session => {
        if (!session.lastModified || !session.title)
            return;
        const age = (now - new Date(session.lastModified)) / (1000 * 60 * 60 * 24);
        if (age <= 7) grouped.last_week.push(session);
        else if (age <= 30) grouped.last_month.push(session);
        else grouped.older.push(session);
    });

    grouped.last_week.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
    grouped.last_month.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
    grouped.older.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
    
    // Render sessions
    for (const [period, sessions] of Object.entries(grouped)) {
        if (sessions.length === 0) continue;
        
        const timeGroup = document.createElement('div');
        timeGroup.className = 'time-group mb-3';
        timeGroup.innerHTML = `
            <div class="time-label">${period.replace('_', ' ')}</div>
            <ul class="list-unstyled">
                ${sessions.map(session => `
                    <li class="conversation-item">
                        <a href="#" class="text-decoration-none text-truncate d-block" 
                            onclick="switchSession('${session.id}'); return false;">
                            ${session.title}
                        </a>
                    </li>
                `).join('')}
            </ul>
        `;
        sessionsList.appendChild(timeGroup);
    }
}

function addSessionToSidebar(session) {
    const sessionsList = document.getElementById('sessionsList');
    const timeGroup = sessionsList.querySelector('.list-unstyled');
    if (!timeGroup) {
        // There aren't any sessions, build the list
        displaySessionsSidebar();
    } else {
        const sessionListEntry = document.createElement('li');
        sessionListEntry.className = "conversation-item";
        sessionListEntry.innerHTML = `<a href="#" class="text-decoration-none text-truncate d-block" 
            onclick="switchSession('${session.id}'); return false;">
            ${session.title}
        </a>`;
        timeGroup.insertBefore(sessionListEntry, timeGroup.firstChild);
    }
}

// Allow sending message with Enter key
document.getElementById('user-input').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// Dependent provider and model dropdowns
document.getElementById('provider').addEventListener('click', function () {
    let provider = this.value;
    let models = document.getElementById("model");
    if (provider === "openai") {
        models.innerHTML = `
            <option selected value="gpt-4o-mini">GPT-4o mini</option>
            <option value="gpt-4o">GPT-4o</option>
        `;
    } else if (provider === "anthropic") {
        models.innerHTML = `
            <option selected value="claude-3-sonnet-20240229">Claude 3 Sonnet</option>
            <option value=claude-3-5-sonnet-20240620">Claude 3.5 Sonnet</option>
        `;
    }
});

// Initialize everything when page loads
document.addEventListener('DOMContentLoaded', async function() {
    displaySessionsSidebar();
    // Check URL for session ID
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session');

    if (sessionId) {
        // Load existing session
        currentSessionId = sessionId;
        await switchSession(sessionId);
    }
    // collapse and expand sidebars
    const leftSidebar = document.getElementById("left-sidebar");
    const rightSidebar = document.getElementById("right-sidebar");
    const toggleLeftIcon = document.querySelector(".bi-layout-text-sidebar-reverse");
    const toggleRightIcon = document.querySelector(".bi-layout-text-sidebar");

    toggleLeftIcon.addEventListener("click", () => {
        leftSidebar.classList.toggle("collapsed");
    });

    toggleRightIcon.addEventListener("click", () => {
        rightSidebar.classList.toggle("collapsed");
    });
});
