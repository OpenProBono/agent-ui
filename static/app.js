function acceptDisclaimer() {
    document.querySelector('.disclaimer').style.display = 'none';
    document.querySelector('.chat-container').style.display = 'block';
    document.querySelector('.file-upload').style.display = 'block';
    document.querySelector('.input-group').style.display = 'flex';
}

function declineDisclaimer() {
    alert('You must accept the disclaimer to use OpenProBono Agents.');
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
    const botMessageContainer = document.createElement('div');
    botMessageContainer.className = 'message bot-message-container';
    botMessageContainer.innerHTML = '<div class="bot-message"></div>';
    chatMessages.appendChild(botMessageContainer);

    // Close any existing SSE connection
    if (eventSource) {
        eventSource.close();
    }

    try {
        // Prepare request data
        const formData = new FormData();
        formData.append('message', userMessage);
        if (userFiles.length > 0) {
            userFiles.forEach((file, index) => {
                formData.append(`file-${index}`, file);
            });
        }

        const response = await fetch('/chat', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            eventSource = new EventSource('/chat');
            eventSource.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleStreamEvent(data, botMessageContainer);
            };
            eventSource.onerror = function(error) {
                console.error('EventSource failed:', error);
                eventSource.close();
                // chatMessages.removeChild(botMessageContainer);
                // addMessageToChat('error', 'An error occurred while streaming the response.');
            };
        } else {
            console.log("An error occurred causing an unexpected response code.")
        }

    } catch (error) {
        console.error('Error:', error);
        addMessageToChat('error', 'An error occurred while sending the message.');
    }
}

function handleStreamEvent(data, container) {
    const botMessageElement = container.querySelector('.bot-message');

    switch(data.type) {
        case 'tool_call':
            content = `<p><i>Tool Call</i></p><br>
            <p><strong>Name:</strong> ${data.name}</p><br>
            <p><strong>Arguments:</strong> ${data.args}</p>`;
            addMessageToChat('tool', content);
            break;
        case 'tool_result':
            botMessageElement.innerHTML += `<p><strong>Tool Result:</strong> ${data.result}</p>`;
            break;
        case 'response':
            const html = marked.parse(data.message);
            const tempContainer = document.createElement('div');
            tempContainer.innerHTML = html;
            
            // Add fade-in class to each new element
            tempContainer.querySelectorAll('*').forEach(el => {
                el.classList.add('bot-message-stream');
            });
            
            botMessageElement.appendChild(tempContainer);
            // addMessageIcons(container);
            // updateSources(data.sources);
            // eventSource.close();
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
    chatMessages.appendChild(messageDiv);
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

function updateSources(sources) {
    const sourceList = document.getElementById('source-list');
    sourceList.innerHTML = ''; // Clear previous sources
    sources.forEach(source => {
        const sourceItem = document.createElement('div');
        sourceItem.className = 'card mb-3';
        sourceItem.innerHTML = `
            <div class="card-body">
                <h5 class="card-title"><a href="${source.url}" target="_blank">${source.title}</a></h5>
                <p class="card-text">${source.text}</p>
            </div>
        `;
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