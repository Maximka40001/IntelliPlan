/**
 * Login Form Handler
 * Handles authentication and form submission
 * @version 2.3.0
 */

(function() {
    'use strict';
    
    const API_ENDPOINTS = {
        LOGIN: '/api/login'
    };
    
    class LoginManager {
        constructor() {
            this.init();
        }
        
        init() {
            const form = document.getElementById('loginForm');
            if (form) {
                form.addEventListener('submit', (e) => this.handleLogin(e));
            }
            
            // Auto-focus username field
            const usernameInput = document.getElementById('username');
            if (usernameInput) {
                usernameInput.focus();
            }
        }
        
        async handleLogin(event) {
            event.preventDefault();
            
            const username = document.getElementById('username')?.value;
            const password = document.getElementById('password')?.value;
            const errorMessage = document.getElementById('errorMessage');
            
            if (!username || !password) {
                this.showError('Заполните все поля');
                return;
            }
            
            // Hide previous errors
            if (errorMessage) {
                errorMessage.classList.remove('show');
            }
            
            // Disable form
            const submitBtn = event.target.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Вход...';
            }
            
            try {
                const response = await fetch(API_ENDPOINTS.LOGIN, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                
                const data = await response.json();
                
                if (response.ok && data.success) {
                    // Success - redirect
                    window.location.href = '/dashboard';
                } else {
                    // Show error
                    this.showError(data.message || 'Ошибка входа');
                    
                    // Re-enable form
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Войти';
                    }
                }
                
            } catch (error) {
                console.error('Login error:', error);
                this.showError('Ошибка соединения с сервером');
                
                // Re-enable form
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Войти';
                }
            }
        }
        
        showError(message) {
            const errorMessage = document.getElementById('errorMessage');
            if (errorMessage) {
                errorMessage.textContent = message;
                errorMessage.classList.add('show');
                
                // Auto-hide after 5 seconds
                setTimeout(() => {
                    errorMessage.classList.remove('show');
                }, 5000);
            }
        }
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new LoginManager());
    } else {
        new LoginManager();
    }
    
})();
