// static/list_sessions.js
document.addEventListener('DOMContentLoaded', () => {
    console.log("list_sessions.js loaded");

    // Add any specific JS needed ONLY for the list_sessions.html page here.
    // For example, maybe some client-side filtering or sorting in the future.
    // Currently, this page primarily relies on server-side rendering and standard form submission.

    const usernameInput = document.getElementById('username');
    const newSessionForm = document.querySelector('.new-session-form form');

    // Optional: Focus the username input on load
    if (usernameInput) {
        usernameInput.focus();
    }

    // Optional: Basic validation before form submission (though backend validation is key)
    if (newSessionForm) {
        newSessionForm.addEventListener('submit', (event) => {
            if (usernameInput && usernameInput.value.trim() === '') {
                alert('Vui lòng nhập tên của bạn.');
                event.preventDefault(); // Stop form submission
            }
            // Add loading indicator maybe?
        });
    }

    // Handle delete button animations and confirmation
    const deleteForms = document.querySelectorAll('.delete-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            
            // Get the session item element
            const sessionItem = this.closest('.session-item');
            
            // Show confirmation dialog
            if (confirm('Bạn có chắc chắn muốn xóa phiên này không?')) {
                // Add deleting class for visual feedback
                sessionItem.classList.add('deleting');
                
                // Submit the form after a short delay for animation
                setTimeout(() => {
                    this.submit();
                }, 300);
            }
        });
    });

    // Auto-hide flash messages after 5 seconds
    const flashMessages = document.querySelectorAll('.flash');
    if (flashMessages.length > 0) {
        setTimeout(() => {
            flashMessages.forEach(message => {
                message.style.opacity = '0';
                setTimeout(() => {
                    message.style.display = 'none';
                }, 500);
            });
        }, 5000);
    }
}); // End DOMContentLoaded