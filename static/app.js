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

let eventSource;
async function sendMessage() {
    const userInput = document.getElementById('user-input');
    const chatMessages = document.getElementById('chat-messages');

    if (userInput.value.trim() === '' && uploadedFiles.length === 0)
        return;

    // Add user message
    addMessageToChat('user', userInput.value);

    // Clear input and file list
    const userMessage = userInput.value;
    const userFiles = uploadedFiles;
    userInput.value = '';
    uploadedFiles = [];
    updateFileList();

    // Create bot message container
    let botMessageContainer = document.createElement('div');
    botMessageContainer.className = 'message bot-message-container';
    botMessageContainer.innerHTML = '<div class="bot-message"></div>';

    // Close any existing SSE connection
    if (eventSource) {
        eventSource.close();
    }

    try {
        // Prepare request data
        const formData = new FormData();
        formData.append('message', userMessage);
        if (userFiles.length > 0) {
            userFiles.forEach((file) => {
                formData.append(`files`, file);
            });
        }

        const response = await fetch('/chat', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            chatMessages.appendChild(botMessageContainer);
            eventSource = new EventSource('/chat');
            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleStreamEvent(data, botMessageContainer);
            };
            eventSource.onerror = function(error) {
                console.error('EventSource failed:', error);
                console.log('EventSource: ', eventSource);
                if (error.target instanceof EventSource && eventSource.readyState === EventSource.CLOSED) {
                    console.error('EventSource closed by server.');
                } else {
                    eventSource.close();
                    console.log('EventSource closed by client.');
                }
                addMessageToChat('error', 'An error occurred while streaming the response.');
            };
        } else {
            addMessageToChat('error', 'An error occurred causing an unexpected response code.');
        }

    } catch (error) {
        console.error('Error: ', error);
        addMessageToChat('error', 'An error occurred while sending your message.');
    }
}

let tempContainer = null;
let processedElements = new Set();
function handleStreamEvent(data, container) {
    const botMessageElement = container.querySelector('.bot-message');

    switch(data.type) {
        case 'tool_call':
            content = `<h5>Tool Call</h5>
            <p><strong>Name:</strong> ${data.name}</p>
            <p><strong>Arguments:</strong> ${data.args}</p>
            <p><i>The tool is gathering sources<span id="${data.id}-dots" class="dots"></span></i></p>`;
            addMessageToChat('tool', content);
            break;
        case 'tool_result':
            updateSources(data.results);
            let toolDots = document.getElementById(`${data.id}-dots`);
            toolDots.classList.remove('dots');
            toolDots.innerHTML = '...finished.';
            break;
        case 'response':
            if (!tempContainer) {
                content = '';
                tempContainer = document.createElement('div');
                processedElements.clear();
            }
            content += data.content;
            const html = marked.parse(content);
            tempContainer.innerHTML = html;
            
            // Add fade-in class to each new element
            tempContainer.querySelectorAll('p, ul li').forEach(el => {
                if (!processedElements.has(el.textContent)) {
                    el.classList.add('bot-message-stream');
                    processedElements.add(el.textContent);
                } else {
                    el.classList.remove('bot-message-stream');
                }
            });
            
            botMessageElement.appendChild(tempContainer);
            tempContainer = null;
            break;
        case 'done':
            if (eventSource) {
                eventSource.close();
                addMessageIcons(container);
            }
            break;
        default:
            console.warn('Unknown event type:', data.type);
    }

    // Scroll to bottom
    container.scrollIntoView({ behavior: 'smooth', block: 'end' });
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
    if (type === 'tool') {
        chatMessages.insertBefore(messageDiv, chatMessages.lastChild);
    } else {
        chatMessages.appendChild(messageDiv);
    }
    messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function addMessageIcons(container) {
    const iconsDiv = document.createElement('div');
    iconsDiv.className = 'message-icons';
    iconsDiv.innerHTML = `
        <i class="bi bi-hand-thumbs-up message-icon" data-bs-toggle="modal" data-bs-target="#likeModal" onclick="setFeedbackAction(this)" title="Like"></i>
        <i class="bi bi-hand-thumbs-down message-icon" data-bs-toggle="modal" data-bs-target="#dislikeModal" onclick="setFeedbackAction(this)" title="Dislike"></i>
        <i class="bi bi-clipboard message-icon" onclick="copyMessage(this)" title="Copy"></i>
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
                    <div>
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
                favicon = `<div style="width:25px; min-width: 25px;"></div>`
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

    // Clear and rebuild the entire list
    sourceList.innerHTML = '';
    
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

function copyMessage(element) {
    const messageText = element.closest('.bot-message-container').querySelector('.bot-message').textContent;
    navigator.clipboard.writeText(messageText).then(() => {
        alert('Message copied to clipboard!');
    });
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