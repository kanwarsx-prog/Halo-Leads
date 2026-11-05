/**
 * SeeMyMind Education Intelligence - Dark / Light Theme Manager
 * Icon-only compact toggle, zero text.
 */
(function () {
    const saved = localStorage.getItem('smm_theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = saved === 'dark' || (!saved && prefersDark);
    if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
})();

function updateThemeToggleButtons(isDark) {
    document.querySelectorAll('.theme-toggle-btn').forEach(btn => {
        const icon = btn.querySelector('.theme-icon') || btn;
        if (icon) icon.textContent = isDark ? '☀️' : '🌙';
        btn.setAttribute('title', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
        btn.setAttribute('aria-label', isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode');
    });
}

function toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const newDark = !isDark;

    if (newDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('smm_theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('smm_theme', 'light');
    }

    updateThemeToggleButtons(newDark);
}

document.addEventListener('DOMContentLoaded', function () {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    updateThemeToggleButtons(isDark);
});
