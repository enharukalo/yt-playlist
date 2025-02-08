// Clear error messages
function clearErrors() {
    const errorDiv = document.getElementById('form-errors');
    if (errorDiv) {
        errorDiv.textContent = '';
        errorDiv.style.opacity = '0';
    }
}

function validateForm(event) {
    const form = event.target;
    clearErrors(); // Clear any existing errors before new validation
    const searchString = form.querySelector('textarea[name="search_string"]').value.trim();
    const youtubeApi = form.querySelector('input[name="youtube_api"]').value;
    let isValid = true;
    
    // Check search string (no more than 5 lines, and no line less than 10 chars)
    const lines = searchString.split('\n');
    if (lines.length > 5) {
        showError("The search string cannot contain more than 5 rows of text.");
        isValid = false;
    }
    
    for (let line of lines) {
        if (line.length > 0 && line.length < 10) {
            showError("Each line in the search string must be at least 10 characters long.");
            isValid = false;
            break;
        }
    }

    // Check YouTube API key if provided
    if (youtubeApi) {
        if (!/^[a-zA-Z0-9\-_]+$/.test(youtubeApi)) {
            showError("YouTube API key must only contain alphanumeric characters, hyphens, or underscores.");
            isValid = false;
        }
        if (youtubeApi.length < 39) {
            showError("YouTube API key must be at least 39 characters long.");
            isValid = false;
        }
    }

    // Additional input validations
    const speed = form.custom_speed.value;
    const start = form.range_start.value;
    const end = form.range_end.value;
    
    if (speed && (speed < 0.1 || speed > 10)) {
        showError('Playback speed must be between 0.1 and 10');
        isValid = false;
    }
    
    if (start && end && parseInt(start) > parseInt(end)) {
        showError('Start video number must be less than end video number');
        isValid = false;
    }

    if (!isValid) {
        event.preventDefault(); // Prevent form submission if validation fails
    }
    
    return isValid;
}

// Better error handling
function showError(message) {
    const errorDiv = document.getElementById('form-errors') || createErrorDiv();
    errorDiv.textContent = message;
    errorDiv.style.opacity = '1';
}

// Create error div if it doesn't exist
function createErrorDiv() {
    const errorDiv = document.createElement('div');
    errorDiv.id = 'form-errors';
    errorDiv.className = 'error-message';
    document.querySelector('form').insertBefore(errorDiv, document.querySelector('form').firstChild);
    return errorDiv;
}