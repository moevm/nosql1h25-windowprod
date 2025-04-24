document.addEventListener('DOMContentLoaded', function() {
    // Проверка статуса аутентификации
    fetch('/api/auth/check')
        .then(response => response.json())
        .then(data => {
            if (data.authenticated) {
                document.getElementById('login-btn').style.display = 'none';
                document.getElementById('logout-btn').style.display = 'block';
            }
        });
});