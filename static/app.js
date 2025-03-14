function acceptDisclaimer() {
    setDisclaimerAccepted(true);
    document.querySelector('.disclaimer').classList.add('d-none');
    document.querySelector('.chat-container').classList.remove('d-none');
    document.querySelector('.file-upload').classList.remove('d-none');
    document.querySelector('.input-group').classList.replace('d-none', 'd-flex');
    document.getElementById('toolbar').classList.replace('d-none', 'd-flex');
}

function declineDisclaimer() {
    setDisclaimerAccepted(false);
}

function getDisclaimerAccepted() {
    return JSON.parse(localStorage.getItem('disclaimerAccepted') || false);
}

function setDisclaimerAccepted(disclaimerAccepted) {
    localStorage.setItem('disclaimerAccepted', JSON.stringify(disclaimerAccepted));
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

function addMessageIcons(container) {
    const iconsDiv = document.createElement('div');
    iconsDiv.className = 'message-icons';
    iconsDiv.innerHTML = `
        <i class="bi bi-hand-thumbs-up icon" data-bs-toggle="modal" data-bs-target="#likeModal" onclick="setFeedbackIndex(${botMessageIndex})" title="Like"></i>
        <i class="bi bi-hand-thumbs-down icon" data-bs-toggle="modal" data-bs-target="#dislikeModal" onclick="setFeedbackIndex(${botMessageIndex})" title="Dislike"></i>
    `;
    container.appendChild(iconsDiv);
}

let feedbackIndex = null;
function setFeedbackIndex(index) {
    feedbackIndex = index;
}

async function sendFeedback(type) {
    let feedbackData = {};

    if (type === 'like') {
        const likeFeedbackText = document.getElementById('likeFeedbackText').value;
        feedbackData.type = 'like';
        feedbackData.comment = likeFeedbackText;
    } else if (type === 'dislike') {
        const dislikeCategories = Array.from(document.querySelectorAll('#dislikeModal .form-check-input:checked'))
            .map(option => option.value);
        const dislikeFeedbackText = document.getElementById('dislikeFeedbackText').value;

        feedbackData.type = 'dislike';
        feedbackData.categories = dislikeCategories;
        feedbackData.comment = dislikeFeedbackText;
    }

    try {
        const formData = new FormData();
        formData.append('data', JSON.stringify(feedbackData));
        formData.append('index', feedbackIndex);
        formData.append('sessionId', currentSessionId);
        const response = await fetch('/feedback', {
            method: 'POST',
            body: formData
        });
        if (response.ok) {
            const data = await response.json();
            const timeoutTime = 8000;
            if (data.status === 'ok') {
                const successAlert = document.getElementById("feedback-success-alert");
                successAlert.classList.remove('d-none');
                successAlert.classList.add('d-block');
                setTimeout(() => {
                    successAlert.classList.remove('d-block');
                    successAlert.classList.add('d-none');
                }, timeoutTime);
            } else {
                const failedAlert = document.getElementById("feedback-failed-alert");
                failedAlert.classList.remove('d-none');
                failedAlert.classList.add('d-block');
                setTimeout(() => {
                    failedAlert.classList.remove('d-block');
                    failedAlert.classList.add('d-none');
                }, timeoutTime);
            }
        }
    } catch (error) {
        console.error('Failed to create new session:', error);
    }

    const modalId = type === 'like' ? '#likeModal' : '#dislikeModal';
    const modal = bootstrap.Modal.getInstance(document.querySelector(modalId));
    modal.hide();
}

function formatDate(dateString) {
    const [year, month, day] = dateString.split('-');
    const months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];
    return `${months[parseInt(month) - 1]} ${parseInt(day)}, ${year}`;
}

function getFirebaseDate() {
    const date = new Date();
    const pad = (num, size = 2) => String(num).padStart(size, '0');
    const year = date.getUTCFullYear();
    const month = pad(date.getUTCMonth() + 1);
    const day = pad(date.getUTCDate());
    const hours = pad(date.getUTCHours());
    const minutes = pad(date.getUTCMinutes());
    const seconds = pad(date.getUTCSeconds());
    const milliseconds = pad(date.getUTCMilliseconds(), 3);
    const microseconds = '000'; // JavaScript does not provide microsecond precision
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}.${milliseconds}${microseconds}+00:00`;
}

function parseInTextCitations(text) {
    /**
     * Parse a text with in-text citations and return a list of objects.
     *
     * @param {string} text - Input text containing in-text citations.
     * @returns {Array} - A list of objects with `text` and `citations` keys.
     */

    // Regex to match citations like [1], [2][3], etc.
    const citationPattern = /\[(\d+(?:\]\[\d+)*)\]/;

    // Split the text based on citations
    const segments = text.split(citationPattern);

    // Track citation instances
    const citationInstances = {};

    const result = [];

    segments.forEach((segment, i) => {
        if (i % 2 === 0) {
            // Even indices are text without citations
            if (segment.trim()) {
                result.push({ text: segment, citations: [] });
            }
        } else {
            // Odd indices are citation groups (e.g., "1", "2][3")
            const citations = segment.split("][").map((citation) => {
                const citationNumber = parseInt(citation, 10);
                citationInstances[citationNumber] = (citationInstances[citationNumber] || 0) + 1;
                return {
                    number: citationNumber,
                    instance: citationInstances[citationNumber],
                };
            });

            // Attach citations to the previous text segment
            if (result.length > 0) {
                result[result.length - 1].citations.push(...citations);
            }
        }
    });

    // Remove trailing text without citations if it exists
    if (result.length > 0 && result[result.length - 1].citations.length === 0) {
        result.pop();
    }

    return result;
}

function addCitationHighlights(e) {
    let highlightColors = [
        "#FFFF99", "#FFDD99", "#FFCC99", "#FFB6B6", "#FFD700", "#B3FF99", "#99FFFF", "#99CCFF", "#B6A8FF", "#FF99CC", 
        "#FFC299", "#FFEB99", "#FFFA99", "#FFD2A6", "#FFF5B7", "#FFF8DC", "#F9E1A7", "#F8C8DC", "#F6C3A4", "#F5B7B1", 
        "#DFFF00", "#F4A300", "#BFFF00", "#00FFFF", "#80FF00", "#A8D5BA", "#FAD02E", "#F4C7B6", "#F9B5B0", "#FCF76E", 
        "#FF8364", "#F0C27B", "#D1B7A1", "#B8F2E6", "#FFD1DC", "#FF89B0", "#D7E4F1", "#CCFFCC", "#E6D8AD", "#F1E1DC", 
        "#A9E9B9", "#A1C6EA", "#FF8A5C", "#9FD5D1", "#E5A3E5", "#FF92A3", "#FFD39B", "#FF5C8D", "#FFE4B5", "#F3D7C1"
    ];

    if (e.target.classList.contains('citation-link')) {
        const citationNum = parseInt(e.target.dataset.citation);
        const instance = parseInt(e.target.dataset.instance);
        const botMsgIndex = parseInt(e.target.dataset.botmsgindex);
        const citationMapping = parseInTextCitations(botMessageTexts[botMsgIndex]);
        
        // Find the substrings for this citation
        let substrings = citationMapping.filter(citedSubstring =>
            citedSubstring.citations.find(citation =>
                citation.number == citationNum && citation.instance == instance
            )
        );

        // Expand source
        const sourceCard = document.getElementById(`card-${citationNum}`);
        const collapseIcon = sourceCard.querySelector('#collapseIcon' + citationNum);
        if (collapseIcon.classList.contains('bi-chevron-up')) {
            // Expand the content
            collapseIcon.classList.replace('bi-chevron-up', 'bi-chevron-down');
            sourceCard.querySelector('#collapseContent' + citationNum).style.display = '';
        }

        // Gather source entities and summary for processing
        const source = Array.from(sourceMap.values()).find(src => src.originalIndex === citationNum - 1);
        const sourceEntities = source.entities;
        const sourceSummary = source.entities[0].metadata.ai_summary;

        const botMessage = document.querySelector(`#bot-message-${botMsgIndex}`);
        // Get all the citation elements inside botMessage
        const citationElements = Array.from(botMessage.querySelectorAll('.citation-link'));
        // Find the part of the response that corresponds to the citation
        let currentCitationIndex = citationElements.indexOf(e.target);
        let previousCitation = currentCitationIndex > 0 ? citationElements[currentCitationIndex - 1] : null;
        while (previousCitation && previousCitation.nextElementSibling === e.target) {
            currentCitationIndex--;
            previousCitation = currentCitationIndex > 0 ? citationElements[currentCitationIndex - 1] : null;
        }
        const prevCitationIndex = previousCitation ? botMessage.innerHTML.indexOf(previousCitation.outerHTML) : 0;
        const currCitationIndex = botMessage.innerHTML.indexOf(e.target.outerHTML);
        // Replace oldText with textToUpdate after all highlights have been added
        let oldText = botMessage.innerHTML.substring(prevCitationIndex, currCitationIndex);
        let textToUpdate = botMessage.innerHTML.substring(prevCitationIndex, currCitationIndex);

        for (const substring of substrings) {
            let matches = [];
        
            sourceEntities.forEach((entity, index) => {
                // Find disjoint longest common substrings and store their position in the substring
                const disjointLCSs = longestDisjointCommonSubstrings(substring.text, entity.text)
                    .filter(lcs => lcs.trim().indexOf(' ') > -1 && isWholeWordSubstring(lcs.trim(), substring.text, entity.text))
                    .map(lcs => {
                        lcs = lcs.trim();
                        const startIndex = substring.text.toLowerCase().indexOf(lcs.toLowerCase());
                        return { text: lcs, length: lcs.length, startIndex, endIndex: startIndex + lcs.length, entityIndex: index };
                    });
                
                matches.push(...disjointLCSs);
            });
        
            if (sourceSummary) {
                const disjointLCSs = longestDisjointCommonSubstrings(substring.text, sourceSummary)
                    .filter(lcs => lcs.trim().indexOf(' ') > -1 && isWholeWordSubstring(lcs.trim(), substring.text, sourceSummary))
                    .map(lcs => {
                        lcs = lcs.trim();
                        const startIndex = substring.text.toLowerCase().indexOf(lcs.toLowerCase());
                        return { text: lcs, length: lcs.length, startIndex, endIndex: startIndex + lcs.length, isSummary: true};
                    });
                
                matches.push(...disjointLCSs);
            }
        
            // Sort matches by length (desc) to prioritize longer matches in case of overlap
            matches.sort((a, b) => b.length - a.length);
            // Track highlighted regions in the substring
            const highlightedRegions = new Array(substring.text.length).fill(false);

            for (const match of matches) {
                let isOverlap = false;
                
                // Check for overlap in the highlighted regions
                for (let i = match.startIndex; i < match.endIndex; i++) {
                    if (highlightedRegions[i]) {
                        isOverlap = true;
                        break;
                    }
                }

                if (isOverlap)
                    continue;

                // If no overlap, proceed to highlight
                for (let i = match.startIndex; i < match.endIndex; i++) {
                    highlightedRegions[i] = true;
                }

                    const colorIndex = Math.floor(Math.random() * highlightColors.length);
                    const color = highlightColors[colorIndex];

                    textToUpdate = textToUpdate.replace(
                        match.text,
                        `<span class="active-highlight" 
                            style="background-color:${color}; cursor: pointer;" 
                            onclick="scrollToHighlight(document.querySelector('#match-${match.startIndex}')); 
                                    return false;">
                            ${match.text}
                        </span>`
                    );

                // Highlight in source or summary as applicable
                if (match.isSummary) {
                    const summaryElement = sourceCard.querySelector(`.ai-summary`);
                    const srcIndex = sourceSummary.toLowerCase().indexOf(match.text.toLowerCase());
                    const srcLcs = sourceSummary.substring(srcIndex, srcIndex + match.text.length);
                        summaryElement.innerHTML = summaryElement.innerHTML.replace(
                            srcLcs,
                            `<span class="active-highlight" id="match-${match.startIndex}" style="background-color:${color};">${srcLcs}</span>`
                        );
                } else {
                    const excerptElement = sourceCard.querySelector(`.list-group-item:nth-child(${match.entityIndex + 1}) div`);
                    const srcIndex = sourceEntities[match.entityIndex].text.toLowerCase().indexOf(match.text.toLowerCase());
                    const srcLcs = sourceEntities[match.entityIndex].text.substring(srcIndex, srcIndex + match.text.length);
                        excerptElement.innerHTML = excerptElement.innerHTML.replace(
                            srcLcs,
                            `<span class="active-highlight" id="match-${match.startIndex}" style="background-color:${color};">${srcLcs}</span>`
                        );
                    }
                }
            }

        // Highlight substring in response
        botMessage.innerHTML = botMessage.innerHTML.replace(oldText, textToUpdate);

        setTimeout(() => {
            const firstHighlight = sourceCard.querySelector('.active-highlight');
            if (firstHighlight) {
                scrollToHighlight(firstHighlight);
            }
        }, 100); // Small delay to allow highlights to be created
    }
}

function processCitations() {
    // Get the bot message container
    const botMessage = document.querySelector(`#bot-message-${botMessageIndex}`);
    // Remove fade in class to add citation links without animation
    botMessage.querySelectorAll('.bot-message-stream').forEach(element => {
        element.classList.remove("bot-message-stream");
    });
    let htmlContent = botMessage.innerHTML;

    // Replace each citation with an interactive link that includes its instance
    let instanceCounters = new Map(); // Track current instance while replacing
    htmlContent = htmlContent.replace(/\[(?:Source\s*)?(\d+)\]/g, (match, num) => {
        const citationNum = parseInt(num);
        // Increment instance counter for this citation number
        if (!instanceCounters.has(citationNum)) {
            instanceCounters.set(citationNum, 1);
        } else {
            instanceCounters.set(citationNum, instanceCounters.get(citationNum) + 1);
        }
        
        const instance = instanceCounters.get(citationNum);
        return `<span class="citation-link" 
                     data-citation="${citationNum}" 
                     data-instance="${instance}"
                     data-botmsgindex="${botMessageIndex}">[${citationNum}]</span>`;
    });

    botMessage.innerHTML = htmlContent;
    document.querySelector("#chat-messages").removeEventListener("click", addCitationHighlights);
    document.querySelector("#chat-messages").addEventListener("click", addCitationHighlights);
}

function longestDisjointCommonSubstrings(s1, s2) {
    const m = s1.length, n = s2.length;
    const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
    const commonSubstrings = [];

    function isWordBoundary(str, pos) {
        return pos === 0 || pos === str.length || /\s/.test(str[pos - 1]) || /\s/.test(str[pos]);
    }

    let s1Lower = s1.toLowerCase();
    let s2Lower = s2.toLowerCase();

    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            if (s1Lower[i - 1] === s2Lower[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
                const start = i - dp[i][j];
                const end = i;

                // Only add substrings that start and end at word boundaries
                if (dp[i][j] > 1 && isWordBoundary(s1, start) && isWordBoundary(s1, end)) {
                    const substring = s1.slice(start, end);
                    commonSubstrings.push({ substring, start, end });
                }
            }
        }
    }

    // Sort by length in descending order to prioritize longest substrings
    commonSubstrings.sort((a, b) => b.substring.length - a.substring.length);

    // Step 2: Select longest disjoint substrings
    const result = [];
    const usedIntervals = [];

    for (const { substring, start, end } of commonSubstrings) {
        let overlap = false;
        for (const [usedStart, usedEnd] of usedIntervals) {
            if (!(end <= usedStart || start >= usedEnd)) {
                overlap = true;
                break;
            }
        }
        if (!overlap) {
            result.push(substring);
            usedIntervals.push([start, end]);
            usedIntervals.sort((a, b) => a[0] - b[0]);
        }
    }

    return result;
}

function isWholeWordSubstring(lcs, str1, str2) {
    // Find positions of the LCS in each string.
    const pos1 = str1.indexOf(lcs);
    const pos2 = str2.toLowerCase().indexOf(lcs.toLowerCase());

    // If the LCS is not found in either string, return false.
    if (pos1 === -1 || pos2 === -1) return false;

    // Define the end positions for LCS in each string.
    const endPos1 = pos1 + lcs.length;
    const endPos2 = pos2 + lcs.length;

    // Check start boundaries in both strings.
    const validStart1 = (pos1 === 0 || !/[a-zA-Z0-9]/.test(str1.charAt(pos1 - 1)));
    const validStart2 = (pos2 === 0 || !/[a-zA-Z0-9]/.test(str2.charAt(pos2 - 1)));

    // Check end boundaries in both strings.
    const validEnd1 = (endPos1 === str1.length || !/[a-zA-Z0-9]/.test(str1.charAt(endPos1)));
    const validEnd2 = (endPos2 === str2.length || !/[a-zA-Z0-9]/.test(str2.charAt(endPos2)));

    // If all boundary checks pass, it's a whole word; otherwise, it’s not.
    return validStart1 && validEnd1 && validStart2 && validEnd2;
}

function scrollToHighlight(element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function clearLoaderMessage() {
    const loaderMsg = document.getElementById("msgLoader");
    if (loaderMsg) {
        // Clear 'Thinking...' message
        loaderMsg.parentElement.outerHTML = '';
    }
}

let eventSource;
let currentSessionId = null;
async function sendMessage() {
    // Extract the bot parameter from the URL
    const pathParts = window.location.pathname.split('/');
    const botId = pathParts[2];  // Assuming the URL is in the form /agent/<bot>
    if (!botId) {
        alert('No bot ID provided in URL.');
        return;
    }

    const userInput = document.getElementById('user-input');
    if (userInput.value.trim() === '' && uploadedFiles.length === 0) return;

    // Hide chatbox placeholder text
    const placeholderChat = document.querySelector('.chat-container .placeholder-text');
    placeholderChat.classList.remove('d-block');
    placeholderChat.classList.add('d-none');

    // Add user message
    addMessageToChat('user', userInput.value);

    // Clear input and file list
    const userMessage = userInput.value;
    const userFiles = uploadedFiles;
    userInput.value = '';
    userInput.style.height = 'auto'; // Reset height to auto so height will be recalculated
    userInput.style.height = (this.scrollHeight) + 'px'; // Set new height based on content
    uploadedFiles = [];
    updateFileList();

    if (eventSource) {
        eventSource.close();
    }

    try {
        if (!currentSessionId) {
            await getNewSession(botId);
        }
        let sessions = loadSavedSessions();
        // If it's a new session, add it to local storage
        if (!sessions.find(session => session.id == currentSessionId)) {
            const newSession = {"title": "New Chat", "lastModified": getFirebaseDate(), "id": currentSessionId, "botId": botId};
            sessions.push(newSession);
            saveSessions(sessions);
            addSessionToSidebar(newSession);
        }
        // Only use FormData if we have files
        if (userFiles.length > 0) {
            const formData = new FormData();
            formData.append('sessionId', currentSessionId);
            userFiles.forEach((file) => {
                formData.append('files', file);
                handleStreamEvent({"type": "file", "id": file.name})
            });

            const response = await fetch('/chat', {
                method: 'POST',
                body: formData
            });
            if (!response.ok) throw new Error('Failed to upload files');
            const uploadResult = await response.json();
            uploadResult.results.forEach((result) => {
                let streamEvent = {
                    "type": "file_upload_result",
                    "id": result.id,
                    "status": result.message,
                }
                handleStreamEvent(streamEvent);
            });
        }
        if (!userMessage) return;

        // Add message loader
        addMessageToChat(
            'bot',
            `<p class="mb-0" id="msgLoader"><i>Thinking<span id="msgLoader-dots" class="dots"></span></i></p>`
        );

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
            clearLoaderMessage();
            addMessageToChat('error', 'An error occurred in the underlying connection.');
        };
    } catch (error) {
        console.error('Error: ', error);
        clearLoaderMessage();
        addMessageToChat('error', 'An error occurred while sending your message.');
    }
}

let botMessageContainer = null;
let botMessageText = '';
let botMessageIndex = 0;
let botMessageTexts = [];
function handleEndOfBotResponse() {
    // Append text to array for citation highlight event handlers
    botMessageTexts.push(botMessageText);
    processCitations();
    botMessageContainer = null;
    botMessageIndex++;
}

function handleStreamEvent(data) {
    switch(data.type) {
        case 'user':
            addMessageToChat(data.type, data.content);
            break;
        case 'file':
            // Add file upload message
            addMessageToChat(
                'tool',
                `<p class="mb-0" id="${data.id}-msg"><i>Uploading ${data.id}<span id="${data.id}-dots" class="dots"></span></i></p>`
            );
            break;
        case 'file_upload_result':
            let fileDots = document.getElementById(`${data.id}-dots`);
            if (!fileDots) {
                // Fetching old conversation so dots were never added, skip
                break;
            }
            fileDots.classList.remove('dots');
            if (data.status === "Success") {
                fileDots.innerHTML = '...finished.';
            } else {
                fileDots.innerHTML = '...failed.';
            }
            break;
        case 'tool_call':
            clearLoaderMessage();
            let argsDict = new Function('return ' + data.args)();
            let toolContent = `<h5>Tool Call</h5>
            <p><strong>Name:</strong> ${data.name}</p>
            <p><strong>Arguments:</strong></p>
            <table class="table table-info">
                <thead>
                    <tr>
                        <th scope="col">Name</th>
                        <th scope="col">Value</th>
                    </tr>
                </thead>
                <tbody>
                    ${Object.keys(argsDict).map(key => `
                        <tr>
                            <td>${key}</td>
                            <td>${argsDict[key]}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
            <p><i>The tool is gathering sources<span id="${data.id}-dots" class="dots"></span></i></p>`;
            addMessageToChat('tool', toolContent);
            if (botMessageContainer) {
                // Append text to array for citation highlight event handlers
                botMessageTexts.push(botMessageText);
                processCitations();
                botMessageContainer = null;
                botMessageIndex++;
            }
            break;
        case 'tool_result':
            updateSources(data.results);
            let toolDots = document.getElementById(`${data.id}-dots`);
            toolDots.classList.remove('dots');
            toolDots.innerHTML = '...finished.';
            break;
        case 'response':
            clearLoaderMessage();
            if (!botMessageContainer) {
                // It's the beginning of a bot message
                // Create bot message container
                botMessageContainer = document.createElement('div');
                botMessageContainer.id = `bot-message-${botMessageIndex}`;
                botMessageContainer.className = 'message bot-message-container';
                botMessageContainer.innerHTML = '<div class="bot-message"></div>';
                addMessageIcons(botMessageContainer);
                // Append it to the chatbox
                const chatMessages = document.getElementById('chat-messages');
                chatMessages.appendChild(botMessageContainer);
                botMessageText = '';
            }
            let content = data.content;
            botMessageText += data.content;
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
        case 'error':
            clearLoaderMessage();
            addMessageToChat('error', 'An error occurred while streaming the response.');
            if (eventSource) {
                eventSource.close();
            }
            break;
        case 'done':
            if (eventSource) {
                eventSource.close();
            }
            if (botMessageContainer) {
                handleEndOfBotResponse();
            }
            let sessions = loadSavedSessions();
            // Get the title if it's a new session
            if (sessions.some((session) => session.id === currentSessionId && session.title === "New Chat")) {
                getCurrentSessionTitle();
            }
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
                downloadUrl = `<p class="card-text"><strong>Original Link</strong>: <a href="${source.entity.metadata.download_url}">${source.entity.metadata.download_url}</a></p>`;
            }
            let summary = '';
            if (Object.hasOwn(source.entity.metadata, 'summary')) {
                summary = `<p class="card-text"><strong>CourtListener Summary</strong>:</p><div class="ms-2">${source.entity.metadata.summary}</div>`;
            }
            aiSummary = '';
            if (Object.hasOwn(source.entity.metadata, 'ai_summary')) {
                mrkdwnSummary = marked.parse(source.entity.metadata.ai_summary);
                aiSummary = `<p class="card-text"><strong>AI Summary</strong>:</p><div class="ms-2 ai-summary">${mrkdwnSummary}</div>`;
            }
            let otherDates = '';
            if (Object.hasOwn(source.entity.metadata, 'other_dates')) {
                otherDates = `<p class="card-text"><strong>Other dates</strong>: ${source.entity.metadata.other_dates}</p>`;
            }
            let caseName = source.entity.metadata.case_name;
            if (caseName.length > 150) {
                caseName = caseName.substring(0, 150) + '...';
            }
            let opinionType = 'Unknown';
            if (Object.hasOwn(source.entity.metadata, 'type')) {
                // possible values: ['010combined', '015unamimous', '020lead', '025plurality', '030concurrence', '035concurrenceinpart', '040dissent', '050addendum', '060remittitur', '070rehearing', '080onthemerits', '090onmotiontostrike']
                switch (source.entity.metadata.type) {
                    case '010combined':
                        opinionType = "Combined";
                        break;
                    case '015unamimous':
                    case '015unaminous':
                        opinionType = "Unanimous";
                        break;
                    case '020lead':
                        opinionType = "Lead";
                        break;
                    case '025plurality':
                        opinionType = "Plurality";
                        break;
                    case '030concurrence':
                        opinionType = "Concurrence";
                        break;
                    case '035concurrenceinpart':
                        opinionType = "Concurrence in Part";
                        break;
                    case '040dissent':
                        opinionType = "Dissent";
                        break;
                    case '050addendum':
                        opinionType = "Addendum";
                        break;
                    case '060remittitur':
                        opinionType = "Remittitur";
                        break;
                    case '070rehearing':
                        opinionType = "Rehearing";
                        break;
                    case '080onthemerits':
                        opinionType = "On the Merits";
                        break;
                    case '090onmotiontostrike':
                        opinionType = "On Motion to Strike";
                        break;
                }
            }
            // Modify the excerpt part to include multiple excerpts
            entitiesHTML = `
                <div class="mt-2">
                    <p class="card-text"><strong>Excerpt${entities.length > 1 ? 's' : ''} (${entities.length})</strong>:</p>
                    <ol class="list-group">
            `;
            entitiesHTML += entities.map(entity => {
                let formattedText = entity.text
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/\n/g, '<br>');
                return `
                    <li class="list-group-item">
                        <div class="p-2" style="border: 2px solid #737373; background-color:#F0F0F0; overflow-y: scroll; max-height: 500px;">${formattedText}</div>
                    </li>
                `;
            }).join('');
            entitiesHTML += '</ol></div>';
            html = `
                <div class="card-header d-flex justify-content-between align-items-center" id="collapseTrigger${index + 1}" style="cursor:pointer;">
                    <i class="fs-2 bi bi-briefcase-fill"></i>
                    <div style="flex: 1; margin: 0 15px;">
                        <h5>${index + 1}. ${caseName}</h5>
                    </div>
                    <i id="collapseIcon${index + 1}" class="bi bi-chevron-up"></i>
                </div>
                <div id="collapseContent${index + 1}" style="display:none;">
                    <div class="card-body">
                        <h6 class="card-subtitle mb-2">${source.entity.metadata.court_name}</h6>
                        <h6 class="card-subtitle mb-2 text-muted">${authorAndDates}</h6>
                        <p class="card-text"><strong>Opinion Type</strong>: ${opinionType}</p>
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
            let urlSource = source.entity.metadata?.source ?? 'Web Search Result';
            let urlTitle = source.entity.metadata?.title ?? 'Title Not Found';
            aiSummary = '';
            if (Object.hasOwn(source.entity.metadata, 'ai_summary')) {
                mrkdwnSummary = marked.parse(source.entity.metadata.ai_summary);
                aiSummary = `<p class="card-text"><strong>AI Summary</strong>:</p><div class="ms-2 ai-summary">${mrkdwnSummary}</div>`;
            }
            entitiesHTML = `
                <div class="mt-2">
                    <p class="card-text"><strong>Excerpt${entities.length > 1 ? 's' : ''} (${entities.length})</strong>:</p>
                    <ol class="list-group">
            `;
            entitiesHTML += entities.map(entity => {
                let formattedText = entity.text
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/\n/g, '<br>')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
                return `
                    <li class="list-group-item">
                        <div class="p-2" style="border: 2px solid #737373; background-color:#F0F0F0; overflow-y: scroll; max-height: 500px;">${formattedText}</div>
                    </li>
                `
            }).join('');
            entitiesHTML += '</ol></div>';
            html = `
                <div class="card-header d-flex justify-content-between align-items-center" id="collapseTrigger${index + 1}" style="cursor:pointer;">
                    <i class="fs-2 bi bi-globe"></i>
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
            entitiesHTML = `
                <div class="mt-2">
                    <p class="card-text"><strong>Excerpt${entities.length > 1 ? 's' : ''} (${entities.length})</strong>:</p>
                    <ol class="list-group">
            `;
            // comma separated unique list of page numbers from entities with that property
            let pageNumbers = entities
                .map(entity => entity.metadata.page_number)
                .filter((value, index, self) => self.indexOf(value) === index);
            let subtitleHTML = pageNumbers ? `
                <h6 class="card-subtitle mb-0">Page${pageNumbers.length > 1 ? 's' : ''} ${pageNumbers.join(', ')}</h6>`
                : '';
            entitiesHTML += entities.map(entity => {
                let formattedText = entity.text
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/\n/g, '<br>')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;');
                return `
                    <li class="list-group-item">
                        <div class="p-2" style="border: 2px solid #737373; background-color:#F0F0F0; overflow-y: scroll; max-height: 500px;">${formattedText}</div>
                    </li>
                `
            }).join('');
            entitiesHTML += '</ol></div>';
            html = `
                <div class="card-header d-flex justify-content-between align-items-center" id="collapseTrigger${index + 1}" style="cursor:pointer;">
                    <i class="fs-2 ${getFileIcon(source.id)}-fill"></i>
                    <div style="flex: 1; margin: 0 15px;">
                        <h5>${index + 1}. ${source.id}</h5>
                        ${subtitleHTML}
                    </div>
                    <i id="collapseIcon${index + 1}" class="bi bi-chevron-up"></i>
                </div>
                <div id="collapseContent${index + 1}" style="display:none;">
                    <div class="card-body">
                        ${entitiesHTML}
                    </div>
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
    // Hide sources placeholder text
    const placeholderSource = document.querySelector('.right-sidebar .placeholder-text');
    placeholderSource.classList.remove('d-block');
    placeholderSource.classList.add('d-none');
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
        sourceItem.id = 'card-' + (i + 1);
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

async function getNewSession(botId) {
    try {
        const response = await fetch(`/agent/${botId}/new_session`);
        if (response.ok) {
            const data = await response.json();
            currentSessionId = data.session_id;
            // Update URL without reloading page, adding session ID to URL
            window.history.pushState({}, '', `/agent/${botId}/session/${currentSessionId}`);
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
    // Display placeholder texts
    const placeholderSource = document.querySelector('.right-sidebar .placeholder-text');
    placeholderSource.classList.remove('d-none');
    placeholderSource.classList.add('d-block');
    const placeholderChat = document.querySelector('.chat-container .placeholder-text');
    placeholderChat.classList.remove('d-none');
    placeholderChat.classList.add('d-block');
    // Remove old highlighted session
    if (currentSessionId) {
        const sessionSidebarEntry = document.getElementById(`session-${currentSessionId}`);
        if (sessionSidebarEntry) {
            sessionSidebarEntry.classList.remove('active-session');
        }
    }
}

async function switchSession(sessionId) {
    clearSessionMessages();

    // Add a status message in case there's an error loading the session
    const statusMsg = document.getElementById("statusMsg");

    // Retrieve session and bot from local storage
    let sessions = loadSavedSessions();
    let session = sessions.find(session => session.id === sessionId);
    let currentBotId = session?.botId;

    if (!currentBotId) {
        statusMsg.innerHTML = "Failed to load session. Check the URL and try again.";
        return;
    }

    // Add new highlighted session
    document.getElementById(`session-${sessionId}`).classList.add('active-session');

    // Update current session
    currentSessionId = sessionId;
    botMessageIndex = 0;
    botMessageTexts = [];

    // Update URL
    window.history.pushState({}, '', `/agent/${currentBotId}/session/${sessionId}`);

    // Hide chatbox placeholder texts
    const placeholderChat = document.querySelector('.chat-container .placeholder-text');
    placeholderChat.classList.remove('d-block');
    placeholderChat.classList.add('d-none');

    // Get bot info
    try {
        const response = await fetch(`/agent/${currentBotId}/info`);
        if (response.ok) {
            const result = await response.json();
            const name = document.getElementById('name');
            const provider = document.getElementById('provider');
            const model = document.getElementById('model');
            const tools = document.getElementById('tools');
            // Capitalize the first letter of each word and replace underscores with spaces
            const displayName = currentBotId.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
            name.innerHTML = `<strong>Name:</strong> ${displayName}`;
            provider.innerHTML = `<strong>Provider:</strong> ${result.data.chat_model.engine}`;
            model.innerHTML = `<strong>Model:</strong> ${result.data.chat_model.model}`;
            tools.innerHTML = '';
            for (const tool of result.data.search_tools) {
                tools.innerHTML += `<li>${tool.name}</li>`;
            }
            for (const tool of result.data.vdb_tools) {
                tools.innerHTML += `<li>${tool.name}</li>`;
            }
        }
    } catch (error) {
        console.error('Failed to load agent:', error);
        addMessageToChat('error', 'Failed to load agent.');
    }

    // Get messages
    try {
        const response = await fetch(`/get_session_messages/${sessionId}`);
        if (response.ok) {
            const messages = await response.json();
            for (const msg of messages.history) {
                if (msg.type === "file") {
                    uploadedFiles.push({name: msg.id});
                    addMessageToChat("user", "");
                    uploadedFiles = [];
                } else {
                    handleStreamEvent(msg);
                    if (msg.type === "response") {
                        handleEndOfBotResponse();
                    }
                }
            }
        }
    } catch (error) {
        console.error('Failed to load session messages:', error);
        addMessageToChat('error', 'Failed to load conversation history.');
    }
}

function clearSession() {
    clearSessionMessages();

    // Extract the bot parameter from the URL
    const pathParts = window.location.pathname.split('/');
    const botId = pathParts[2];  // Assuming the URL is in the form /agent/<bot>

    // Update URL to remove session ID but retain bot
    if (botId) {
        window.history.pushState({}, '', `/agent/${botId}`);
    } else {
        console.error('Unable to retrieve bot ID.');
    }

    // Clear session variables
    currentSessionId = null;
    botMessageIndex = 0;
    botMessageTexts = [];
}

async function getCurrentSessionTitle() {
    const response = await fetch(`/sessions?ids[]=${currentSessionId}`);
    if (!response.ok) throw new Error('Failed to get sessions from server');
    let fetchedSessions = await response.json();
    let savedSessions = loadSavedSessions();
    // if savedSessions contains a session with id === fetchedSessions[0].id,
    // then replace it with the fetched session
    if (savedSessions.some((session) => session.id === fetchedSessions[0].id)) {
        savedSessions[savedSessions.findIndex((session) => session.id === fetchedSessions[0].id)] = fetchedSessions[0];
        saveSessions(savedSessions);
        // update title in sidebar
        const titleElement = document.querySelector(`#session-${currentSessionId} a`);
        titleElement.innerText = fetchedSessions[0].title;
        titleElement.title = fetchedSessions[0].title;
    }
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
        today: [],
        past_week: [],
        past_month: [],
        older: []
    };
    
    const now = new Date();
    sessions.forEach(session => {
        if (!session.lastModified || !session.title)
            return;
        const lastModified = new Date(session.lastModified);
        const ageInDays = (now - lastModified) / (1000 * 60 * 60 * 24);

        if (lastModified.toDateString() === now.toDateString()) {
            grouped.today.push(session);
        } else if (ageInDays <= 7) {
            grouped.past_week.push(session);
        } else if (ageInDays <= 30) {
            grouped.past_month.push(session);
        } else {
            grouped.older.push(session);
        }
    });

    // Sort sessions within each group
    for (const sessions of Object.values(grouped)) {
        sessions.sort((a, b) => new Date(b.lastModified) - new Date(a.lastModified));
    }

    // Render sessions
    for (const [period, sessions] of Object.entries(grouped)) {
        if (sessions.length === 0) continue;
        
        const timeGroup = document.createElement('div');
        timeGroup.className = 'time-group mb-3';
        timeGroup.innerHTML = `
            <div class="time-label">${period.replace('_', ' ')}</div>
            <ul class="list-unstyled">
                ${sessions.map(session => `
                    <li id="session-${session.id}" class="conversation-item">
                        <a href="#" class="text-decoration-none text-truncate d-block" 
                            onclick="switchSession('${session.id}'); return false;"
                            title="${session.title ? session.title : "Untitled Chat"}">
                            ${session.title ? session.title : "Untitled Chat"}
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
        sessionListEntry.id = `session-${session.id}`;
        sessionListEntry.innerHTML = `<a href="#" class="text-decoration-none text-truncate d-block" 
            onclick="switchSession('${session.id}'); return false;">
            ${session.title}
        </a>`;
        timeGroup.insertBefore(sessionListEntry, timeGroup.firstChild);
    }
}

function toggleSidebar(side) {
    const leftSidebar = document.getElementById('left-sidebar');
    const rightSidebar = document.getElementById('right-sidebar');
    
    // Check if we're on mobile
    if (window.innerWidth <= 767) {
        if (side === 'left') {
            // If toggling left sidebar
            leftSidebar.classList.toggle('collapsed');
            // Ensure right sidebar is collapsed
            rightSidebar.classList.add('collapsed');
        } else if (side === 'right') {
            // If toggling right sidebar
            rightSidebar.classList.toggle('collapsed');
            // Ensure left sidebar is collapsed
            leftSidebar.classList.add('collapsed');
        }
    } else {
        // On desktop, normal toggle behavior
        if (side === 'left') {
            leftSidebar.classList.toggle('collapsed');
        } else if (side === 'right') {
            rightSidebar.classList.toggle('collapsed');
        }
    }
}

// Allow sending message with Enter key
document.getElementById('user-input').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendMessage();
    }
});

// Dynamic size for user input textarea
document.getElementById('user-input').addEventListener('input', function() {
    this.style.height = 'auto'; // Reset height to auto so height will be recalculated
    this.style.height = (this.scrollHeight) + 'px'; // Set new height based on content
});

// Initialize everything when page loads
document.addEventListener('DOMContentLoaded', async function() {
    // Check if disclaimer has been accepted
    const disclaimerAccepted = getDisclaimerAccepted();
    if (!disclaimerAccepted) {
        document.querySelector('.disclaimer').classList.remove('d-none');
        document.querySelector('.chat-container').classList.add('d-none');
        document.querySelector('.file-upload').classList.add('d-none');
        document.querySelector('.input-group').classList.replace('d-flex', 'd-none');
        document.getElementById('toolbar').classList.replace('d-flex', 'd-none');
    }
    displaySessionsSidebar();

    // Disable send while checking if server is alive
    document.getElementById("sendButton").setAttribute("disabled", "");
    const statusMsg = document.getElementById("statusMsg");
    try {
        const response = await fetch('/status');
        if (response.ok) {
            const result = await response.json();
            if (result.status != "ok") {
                statusMsg.innerHTML = "Agents are currently unavailable. Please try again later.";
                return;
            } else {
                // Status ok, enable send button
                document.getElementById("sendButton").removeAttribute("disabled");
                statusMsg.innerHTML = "";
            }
        }
    } catch (error) {
        statusMsg.innerHTML = "Agents are currently unavailable. Please try again later.";
        return;
    }

    // Extract the session parameter from the URL
    const pathParts = window.location.pathname.split('/');
    const sessionId = pathParts[4];  // Assuming the URL is in the form /agent/<bot>/session/<session>
    if (sessionId) {
        // Load existing session
        currentSessionId = sessionId;
        await switchSession(sessionId);
    }
});
