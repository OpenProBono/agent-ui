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

    document.getElementById('fileInput').value = '';
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

document.addEventListener('DOMContentLoaded', function() {
    // disable filter buttons until server responds
    const applyButton = document.getElementById('filterButton');
    const clearButton = document.getElementById('resetButton');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');
    applyButton.disabled = true;
    clearButton.disabled = true;
    
    // Handle resource checkboxes for multiple selection
    const handleCheckboxes = () => {
        const checkedBoxes = document.querySelectorAll('.resource-checkbox:checked');
        if (checkedBoxes.length > 0) {
            deleteSelectedBtn.style.display = 'inline-block';
            deleteSelectedBtn.textContent = `Delete Selected (${checkedBoxes.length})`;
        } else {
            deleteSelectedBtn.style.display = 'none';
        }
    };
    
    // Add event listeners to all checkboxes
    document.querySelectorAll('.resource-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', handleCheckboxes);
    });
    
    // Select All button
    const selectAllBtn = document.getElementById('selectAllBtn');
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function() {
            document.querySelectorAll('.resource-checkbox').forEach(checkbox => {
                checkbox.checked = true;
            });
            handleCheckboxes();
        });
    }
    
    // Deselect All button
    const deselectAllBtn = document.getElementById('deselectAllBtn');
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', function() {
            document.querySelectorAll('.resource-checkbox').forEach(checkbox => {
                checkbox.checked = false;
            });
            handleCheckboxes();
        });
    }
    
    // Extract collection name from URL path
    const collectionId = window.location.pathname.split('/').pop();
    
    // call get_resource_count() endpoint with collection parameter
    fetch(`/resource_count/${collectionId}`)
        .then(response => response.json())
        .then(data => {
            if (data["message"] == "Success") {
                let resourceDlg = `There are currently ${data["resource_count"].toLocaleString()} excerpts indexed.`;
                if (data["resource_count"] == 1) {
                    resourceDlg = "There is currently 1 excerpt indexed.";
                }
                document.getElementById('resource-count').innerHTML = resourceDlg;
                applyButton.disabled = data["resource_count"] > 0 ? false : true;
                clearButton.disabled = data["resource_count"] > 0 ? false : true;
            } else {
                document.getElementById('resource-count').innerHTML = `Unable to index resources.`;
            }
        })
        .catch(() => {
            document.getElementById('resource-count').innerHTML = `Unable to index resources.`;
        });

    // Add Resource Modal Functionality
    const addResourceBtn = document.getElementById('addResourceBtn');
    const addResourceModal = new bootstrap.Modal(document.getElementById('addResourceModal'));
    const resourceTypeSelect = document.getElementById('resourceType');
    const urlInputGroup = document.getElementById('urlInputGroup');
    const fileInputGroup = document.getElementById('fileInputGroup');
    const submitAddResource = document.getElementById('submitAddResource');

    // Show/hide appropriate input fields based on resource type
    resourceTypeSelect.addEventListener('change', function() {
        urlInputGroup.style.display = 'none';
        fileInputGroup.style.display = 'none';
        
        const selectedType = this.value;
        if (selectedType === 'url') {
            urlInputGroup.style.display = 'block';
        } else if (selectedType === 'file') {
            fileInputGroup.style.display = 'block';
        }
    });

    // Open Add Resource Modal
    addResourceBtn.addEventListener('click', function() {
        addResourceModal.show();
    });
    
    // Handle Add Resource Submission
    submitAddResource.addEventListener('click', async function() {
        const resourceType = resourceTypeSelect.value;
        if (!resourceType) {
            alert('Please select a resource type');
            return;
        }
        
        let isValid = true;
        let resourcesAdded = 0;
        let resourcesFailed = 0;
        
        submitAddResource.disabled = true;
        submitAddResource.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Adding...';
        
        try {
            if (resourceType === 'url') {
                const urlInput = document.getElementById('urlInput');
                const urls = urlInput.value.split('\n').filter(url => url.trim() !== '');
                
                if (urls.length === 0) {
                    alert('Please enter at least one URL');
                    isValid = false;
                } else {
                    const formData = new FormData();
                    formData.append('resource_type', resourceType);
                    urls.forEach(url => {
                        formData.append('urls', url.trim());
                    });
                    
                    try {
                        const response = await fetch(`/upload_resources/${collectionId}`, {
                            method: 'POST',
                            body: formData
                        });
                        const data = await response.json();
                        if (data.message === 'Success') {
                            resourcesAdded = urls.length;
                        } else {
                            resourcesFailed = urls.length;
                            console.error(`Error adding URLs: ${data.details || data.message}`);
                        }
                    } catch (error) {
                        resourcesFailed = urls.length;
                        console.error(`Error adding URLs: ${error}`);
                    }
                }
            } else if (resourceType === 'file') {
                if (!uploadedFiles || uploadedFiles.length === 0) {
                    alert('Please select at least one file');
                    isValid = false;
                } else {
                    const formData = new FormData();
                    formData.append('resource_type', resourceType);
                    uploadedFiles.forEach(file => {
                        formData.append('files', file);
                    });
                    
                    try {
                        console.log(formData);
                        const response = await fetch(`/upload_resources/${collectionId}`, {
                            method: 'POST',
                            body: formData
                        });
                        const data = await response.json();
                        if (data.message === 'Success') {
                            resourcesAdded = uploadedFiles.length;
                        } else {
                            resourcesFailed = uploadedFiles.length;
                            console.error(`Error adding files: ${data.details || data.message}`);
                        }
                    } catch (error) {
                        resourcesFailed = uploadedFiles.length;
                        console.error(`Error adding files: ${error}`);
                    }
                }
            }
            
            if (isValid) {
                if (resourcesAdded > 0) {
                    let message = `Successfully added ${resourcesAdded} resource${resourcesAdded !== 1 ? 's' : ''}`;
                    if (resourcesFailed > 0) {
                        message += `, failed to add ${resourcesFailed} resource${resourcesFailed !== 1 ? 's' : ''}`;
                    }
                    addResourceModal.hide();
                    alert(message);
                    // Refresh the page to show the new resources
                    window.location.reload();
                } else if (resourcesFailed > 0) {
                    alert(`Failed to add any resources. ${resourcesFailed} resource${resourcesFailed !== 1 ? 's' : ''} failed.`);
                }
            }
        } finally {
            submitAddResource.disabled = false;
            submitAddResource.innerHTML = 'Add Resource';
            uploadedFiles = [];
            updateFileList();
        }
    });

    // collapse filters
    let filtersCollapsed = false;
    document.getElementById("collapseTrigger").addEventListener('click', function() {
        const collapseIcon = document.getElementById("collapseIcon");
        const collapseContent = document.getElementById("collapseContent");
        
        if (!filtersCollapsed) {
            collapseIcon.classList.replace("bi-chevron-down", "bi-chevron-up");
            collapseContent.style.display = "none";
        } else {
            collapseIcon.classList.replace("bi-chevron-up", "bi-chevron-down");
            collapseContent.style.display = "block";
        }
        filtersCollapsed = !filtersCollapsed;
    });

    // Check/Clear All Jurisdictions
    document.getElementById('checkAllJurisdictions').addEventListener('click', function() {
        document.querySelectorAll('.form-check-input').forEach(input => input.checked = true);
    });

    document.getElementById('clearAllJurisdictions').addEventListener('click', function() {
        document.querySelectorAll('.form-check-input').forEach(input => input.checked = false);
    });

    // Loading animation for the filter button
    document.getElementById("browseForm").addEventListener('submit', function(event) {
        event.preventDefault();

        // Check which button submitted the form
        if (event.submitter.id === "resetButton") {
            event.submitter.disabled = true;
            event.submitter.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Resetting...';
            window.location.href = window.location.pathname;
            return;
        }

        const button = document.getElementById("filterButton");
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Applying...';

        // Get the form data
        const formData = new FormData(this);
        const params = new URLSearchParams();

        // Only include source if non-empty
        const source = formData.get('source');
        if (source) {
            params.append('source', source);
        }

        // Only include keyword if non-empty
        const keyword = formData.get('keyword');
        if (keyword) {
            params.append('keyword', keyword);
        }
        
        // Only include dates if non-empty
        const afterDate = formData.get('after_date');
        if (afterDate) {
            params.append('after_date', afterDate);
        }
        
        const beforeDate = formData.get('before_date');
        if (beforeDate) {
            params.append('before_date', beforeDate);
        }
        
        // Only include jurisdictions if not all are selected
        const selectedJurisdictions = formData.getAll('jurisdictions');
        const allJurisdictionCheckboxes = document.querySelectorAll('input[name="jurisdictions"]');
        if (selectedJurisdictions.length < allJurisdictionCheckboxes.length) {
            selectedJurisdictions.forEach(j => params.append('jurisdictions', j));
        }
        
        const perPage = formData.get('per_page');
        if (perPage !== '50') {
            params.append('per_page', perPage);
        }

        // Navigate to the URL with search parameters
        const queryString = params.toString();
        window.location.href = window.location.pathname + (queryString ? '?' + queryString : '');
    });


    // Make source cards collapsible
    // loop starting at 1 until there are no more source cards with id "collapseTrigger" followed by a number
    for (let i = 0; document.getElementById('collapseTrigger' + (i + 1)); i++) {
        document.getElementById('collapseTrigger' + (i + 1)).addEventListener('click', (e) => {
            // Don't collapse/expand if the user clicked on the checkbox
            if (e.target.classList.contains('form-check-input')) {
                return;
            }
            
            const collapseIcon = document.getElementById('collapseIcon' + (i + 1));
            if (collapseIcon.classList.contains('bi-chevron-down')) {
                // Collapse the content
                collapseIcon.classList.replace('bi-chevron-down', 'bi-chevron-up');
                document.getElementById('collapseContent' + (i + 1)).style.display = 'none';
            } else {
                // Expand the content
                collapseIcon.classList.replace('bi-chevron-up', 'bi-chevron-down');
                document.getElementById('collapseContent' + (i + 1)).style.display = '';
            }
        });
    }
    
    // Handle bulk resource deletion
    deleteSelectedBtn.addEventListener('click', async function() {
        const checkedBoxes = document.querySelectorAll('.resource-checkbox:checked');
        
        if (checkedBoxes.length === 0) {
            alert('No resources selected');
            return;
        }
        
        if (confirm(`Are you sure you want to delete ${checkedBoxes.length} selected resource${checkedBoxes.length !== 1 ? 's' : ''}?`)) {
            deleteSelectedBtn.disabled = true;
            deleteSelectedBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
            
            let resourcesDeleted = 0;
            let resourcesFailed = 0;
            
            for (const checkbox of checkedBoxes) {
                const resourceId = checkbox.getAttribute('data-resource-id');
                const resourceType = checkbox.getAttribute('data-resource-type');
                
                const formData = new FormData();
                formData.append('resource_id', resourceId);
                formData.append('resource_type', resourceType);
                
                try {
                    const response = await fetch(`/remove_resource/${collectionId}`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    
                    if (data.message === 'Success') {
                        resourcesDeleted++;
                        
                        // Find the card that contains this checkbox and remove it
                        const card = checkbox.closest('.card');
                        if (card) {
                            card.remove();
                        }
                    } else {
                        resourcesFailed++;
                        console.error(`Error deleting resource ${resourceId}: ${data.details || data.message}`);
                    }
                } catch (error) {
                    resourcesFailed++;
                    console.error(`Error deleting resource ${resourceId}: ${error}`);
                }
            }
            
            if (resourcesDeleted > 0) {
                let message = `Successfully deleted ${resourcesDeleted} resource${resourcesDeleted !== 1 ? 's' : ''}`;
                if (resourcesFailed > 0) {
                    message += `, failed to delete ${resourcesFailed} resource${resourcesFailed !== 1 ? 's' : ''}`;
                }
                alert(message);
            } else if (resourcesFailed > 0) {
                alert(`Failed to delete any resources. ${resourcesFailed} resource${resourcesFailed !== 1 ? 's' : ''} failed.`);
            }
            
            deleteSelectedBtn.disabled = false;
            deleteSelectedBtn.style.display = 'none';
        }
    });
});