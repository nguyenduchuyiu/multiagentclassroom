document.addEventListener('DOMContentLoaded', () => {
    const problemSelect = document.getElementById('problem_id');
    const previewArea = document.getElementById('problem-preview-area');
    const previewContent = previewArea.querySelector('.preview-content');
    const form = document.getElementById('problem-selection-form');
    const loadingOverlay = document.getElementById('loading-overlay');
    const submitButton = form.querySelector('.submit-button');

    // Fetch problems
    fetch('/api/problems')
        .then(response => response.json())
        .then(problems => {
            if (problems && problems.length > 0) {
                problems.forEach(problem => {
                    const option = document.createElement('option');
                    option.value = problem.id;
                    option.textContent = problem.text.length > 100 ? 
                        problem.text.substring(0, 97) + "..." : problem.text;
                    option.dataset.fulltext = problem.text;
                    problemSelect.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.value = "";
                option.textContent = "No problems available.";
                problemSelect.appendChild(option);
                problemSelect.disabled = true;
                submitButton.disabled = true;
                submitButton.classList.add('disabled');
            }
        })
        .catch(error => {
            console.error('Error fetching problems:', error);
            previewContent.textContent = 'Error loading problem list.';
            previewArea.style.display = 'block';
            problemSelect.disabled = true;
            submitButton.disabled = true;
            submitButton.classList.add('disabled');
        });

    // Handle problem selection
    problemSelect.addEventListener('change', (event) => {
        const selectedOption = event.target.selectedOptions[0];
        if (selectedOption && selectedOption.value) {
            previewContent.textContent = selectedOption.dataset.fulltext;
            previewArea.style.display = 'block';
            previewArea.classList.add('show');
        } else {
            previewArea.style.display = 'none';
            previewArea.classList.remove('show');
            previewContent.textContent = '';
        }
    });

    // Handle form submission
    form.addEventListener('submit', (e) => {
        loadingOverlay.style.display = 'flex';
        submitButton.disabled = true;
        submitButton.classList.add('loading');
    });
});