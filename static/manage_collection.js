document.addEventListener('DOMContentLoaded', function() {
    // disable filter buttons until server responds
    const applyButton = document.getElementById('filterButton');
    const clearButton = document.getElementById('resetButton');
    applyButton.disabled = true;
    clearButton.disabled = true;
    
    // Extract collection name from URL path
    const collectionName = window.location.pathname.split('/').pop();
    
    // call get_resource_count() endpoint with collection parameter
    fetch(`/resource_count/${collectionName}`)
        .then(response => response.json())
        .then(data => {
            if (data["message"] == "Success") {
                document.getElementById('resource-count').innerHTML = `There are currently ${data["resource_count"].toLocaleString()} resources indexed.`;
                applyButton.disabled = false;
                clearButton.disabled = false;
            } else {
                document.getElementById('resource-count').innerHTML = `Unable to index resources.`;
            }
        })
        .catch(() => {
            document.getElementById('resource-count').innerHTML = `Unable to index resources.`;
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
        document.getElementById('collapseTrigger' + (i + 1)).addEventListener('click', () => {
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
});