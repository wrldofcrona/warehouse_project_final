
// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация всплывающих подсказок
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(tooltip => {
        new bootstrap.Tooltip(tooltip);
    });
    
    // Инициализация всплывающих окон
    const popovers = document.querySelectorAll('[data-bs-toggle="popover"]');
    popovers.forEach(popover => {
        new bootstrap.Popover(popover);
    });
    
    // Автоматическое скрытие уведомлений
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            bootstrap.Alert.getOrCreateInstance(alert).close();
        }, 5000);
    });
    
    // Валидация форм
    const forms = document.querySelectorAll('.needs-validation');
    forms.forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });
    
    // Динамическое обновление времени
    updateClock();
    setInterval(updateClock, 60000); // Обновлять каждую минуту
});

// Функция обновления времени
function updateClock() {
    const now = new Date();
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        timeElement.textContent = now.toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

// Функция подтверждения действия
function confirmAction(message = 'Вы уверены, что хотите выполнить это действие?') {
    return confirm(message);
}

// Функция показа загрузки
function showLoading(element) {
    element.classList.add('loading');
    element.disabled = true;
}

// Функция скрытия загрузки
function hideLoading(element) {
    element.classList.remove('loading');
    element.disabled = false;
}

// Функция показа уведомления
function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container') || document.body;
    container.insertBefore(notification, container.firstChild);
    
    setTimeout(() => {
        bootstrap.Alert.getOrCreateInstance(notification).close();
    }, 5000);
}

// Функция для динамического обновления данных
function updateData(url, callback) {
    fetch(url)
        .then(response => response.json())
        .then(data => {
            if (callback && typeof callback === 'function') {
                callback(data);
            }
        })
        .catch(error => {
            console.error('Ошибка при обновлении данных:', error);
            showNotification('Ошибка при обновлении данных', 'danger');
        });
}

// Функция для фильтрации таблиц
function filterTable(tableId, searchId) {
    const searchInput = document.getElementById(searchId);
    const table = document.getElementById(tableId);
    
    if (!searchInput || !table) return;
    
    searchInput.addEventListener('keyup', function() {
        const filter = this.value.toLowerCase();
        const rows = table.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(filter) ? '' : 'none';
        });
    });
}

// Функция для сортировки таблиц
function sortTable(tableId, columnIndex) {
    const table = document.getElementById(tableId);
    if (!table) return;
    
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const isAscending = table.dataset.sortOrder !== 'asc';
    
    rows.sort((a, b) => {
        const aValue = a.children[columnIndex].textContent.trim();
        const bValue = b.children[columnIndex].textContent.trim();
        
        // Пытаемся сравнить как числа
        const aNum = parseFloat(aValue.replace(/[^0-9.-]+/g, ''));
        const bNum = parseFloat(bValue.replace(/[^0-9.-]+/g, ''));
        
        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAscending ? aNum - bNum : bNum - aNum;
        }
        
        // Иначе сравниваем как строки
        return isAscending 
            ? aValue.localeCompare(bValue, 'ru')
            : bValue.localeCompare(aValue, 'ru');
    });
    
    // Обновляем порядок строк
    rows.forEach(row => tbody.appendChild(row));
    
    // Обновляем индикатор сортировки
    table.dataset.sortOrder = isAscending ? 'asc' : 'desc';
    
    // Обновляем заголовки
    const headers = table.querySelectorAll('thead th');
    headers.forEach((header, index) => {
        header.classList.remove('sort-asc', 'sort-desc');
        if (index === columnIndex) {
            header.classList.add(isAscending ? 'sort-asc' : 'sort-desc');
        }
    });
}

// Функция для экспорта данных
function exportData(format = 'csv') {
    const table = document.querySelector('table');
    if (!table) return;
    
    let data = '';
    
    // Заголовки
    const headers = [];
    table.querySelectorAll('thead th').forEach(header => {
        headers.push(header.textContent.trim());
    });
    data += headers.join(',') + '\n';
    
    // Данные
    table.querySelectorAll('tbody tr').forEach(row => {
        const cells = [];
        row.querySelectorAll('td').forEach(cell => {
            cells.push(cell.textContent.trim());
        });
        data += cells.join(',') + '\n';
    });
    
    // Создаем и скачиваем файл
    const blob = new Blob([data], { type: 'text/csv' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `warehouse_export_${new Date().toISOString().slice(0,10)}.csv`;
    link.click();
}

// Функция для создания графика
function createChart(ctx, type, data, options = {}) {
    return new Chart(ctx, {
        type: type,
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            ...options
        }
    });
}

// Глобальные слушатели событий
document.addEventListener('click', function(e) {
    // Обработка кликов на ссылках с подтверждением
    if (e.target.matches('[data-confirm]')) {
        if (!confirmAction(e.target.dataset.confirm)) {
            e.preventDefault();
        }
    }
    
    // Обработка кликов на кнопках с загрузкой
    if (e.target.matches('[data-loading]')) {
        showLoading(e.target);
    }
});

// Добавление стилей для сортировки
const style = document.createElement('style');
style.textContent = `
    .sort-asc::after {
        content: ' ▲';
        font-size: 0.8em;
    }
    
    .sort-desc::after {
        content: ' ▼';
        font-size: 0.8em;
    }
    
    th {
        cursor: pointer;
        user-select: none;
    }
    
    th:hover {
        background-color: rgba(0,0,0,0.05);
    }
`;
document.head.appendChild(style);