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

}); // End DOMContentLoaded