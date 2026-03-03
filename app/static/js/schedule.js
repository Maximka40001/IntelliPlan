/**
 * Schedule Management Module
 * Handles schedule filtering, loading, and display
 * @version 2.3.0
 */

(function() {
    'use strict';
    
    const API_ENDPOINTS = {
        SCHEDULE: '/api/schedule',
        STATS: '/api/stats'
    };
    
    class ScheduleManager {
        constructor() {
            this.cache = new Map();
            this.cacheTimeout = 5 * 60 * 1000; // 5 minutes
        }
        
        async applyFilters() {
            const group = document.getElementById('groupFilter')?.value;
            const dateFrom = document.getElementById('dateFrom')?.value;
            const dateTo = document.getElementById('dateTo')?.value;
            
            const params = new URLSearchParams();
            if (group && group !== 'all') params.append('group', group);
            if (dateFrom) params.append('date_from', dateFrom);
            if (dateTo) params.append('date_to', dateTo);
            
            const cacheKey = params.toString();
            
            // Check cache
            if (this.cache.has(cacheKey)) {
                const cached = this.cache.get(cacheKey);
                if (Date.now() - cached.timestamp < this.cacheTimeout) {
                    this.renderSchedule(cached.data);
                    return;
                }
            }
            
            try {
                const url = `${API_ENDPOINTS.SCHEDULE}?${params}`;
                const response = await fetch(url);
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                
                const data = await response.json();
                
                // Cache the result
                this.cache.set(cacheKey, {
                    data: data,
                    timestamp: Date.now()
                });
                
                this.renderSchedule(data);
                
            } catch (error) {
                console.error('Error loading schedule:', error);
                this.showError('Ошибка загрузки расписания');
            }
        }
        
        renderSchedule(data) {
            const tbody = document.getElementById('scheduleTableBody');
            if (!tbody) {
                console.error('Schedule table body not found');
                return;
            }
            
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align: center;">Расписание не найдено</td></tr>';
                return;
            }
            
            // Use DocumentFragment for better performance
            const fragment = document.createDocumentFragment();
            
            data.forEach(item => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td><span class="date-badge">${this.escapeHtml(item.date)}</span></td>
                    <td>${this.escapeHtml(item.day_name)}</td>
                    <td><span class="time-badge">${this.escapeHtml(item.time)}</span></td>
                    <td><strong>${this.escapeHtml(item.group_name)}</strong></td>
                    <td>${this.escapeHtml(item.subject_name)}</td>
                    <td>${this.escapeHtml(item.teacher_name)}</td>
                    <td>${this.escapeHtml(item.classroom)}</td>
                `;
                fragment.appendChild(row);
            });
            
            tbody.innerHTML = '';
            tbody.appendChild(fragment);
        }
        
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        showError(message) {
            const tbody = document.getElementById('scheduleTableBody');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--error-color);">${this.escapeHtml(message)}</td></tr>`;
            }
        }
        
        clearCache() {
            this.cache.clear();
        }
    }
    
    // Initialize and expose globally
    window.scheduleManager = new ScheduleManager();
    
    // Setup global function for backward compatibility
    window.applyFilters = function() {
        return window.scheduleManager.applyFilters();
    };
    
})();
