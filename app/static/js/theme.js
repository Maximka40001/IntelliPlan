/**
 * Theme Management Module
 * Handles dark/light theme switching with localStorage persistence
 * @version 2.3.0
 */

(function() {
    'use strict';
    
    const THEME_KEY = 'schedule-theme';
    const THEME_DARK = 'dark';
    const THEME_LIGHT = 'light';
    
    class ThemeManager {
        constructor() {
            this.currentTheme = this.loadTheme();
            this.init();
        }
        
        init() {
            this.applyTheme(this.currentTheme);
            this.setupToggleButton();
        }
        
        loadTheme() {
            const saved = localStorage.getItem(THEME_KEY);
            if (saved) return saved;
            
            // Check system preference
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                return THEME_DARK;
            }
            
            return THEME_LIGHT;
        }
        
        saveTheme(theme) {
            localStorage.setItem(THEME_KEY, theme);
        }
        
        applyTheme(theme) {
            document.documentElement.setAttribute('data-theme', theme);
            this.currentTheme = theme;
            this.updateToggleButton();
        }
        
        toggleTheme() {
            const newTheme = this.currentTheme === THEME_DARK ? THEME_LIGHT : THEME_DARK;
            this.applyTheme(newTheme);
            this.saveTheme(newTheme);
        }
        
        setupToggleButton() {
            const btn = document.getElementById('themeToggle');
            if (!btn) {
                console.warn('Theme toggle button not found');
                return;
            }
            
            btn.addEventListener('click', () => this.toggleTheme());
        }
        
        updateToggleButton() {
            const btn = document.getElementById('themeToggle');
            if (!btn) return;
            
            const icon = this.currentTheme === THEME_DARK ? '☀️' : '🌙';
            const text = this.currentTheme === THEME_DARK ? 'Светлая' : 'Тёмная';
            btn.innerHTML = `${icon} <span>${text}</span>`;
        }
    }
    
    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => new ThemeManager());
    } else {
        new ThemeManager();
    }
    
    // Expose to global scope for external access
    window.ThemeManager = ThemeManager;
})();
