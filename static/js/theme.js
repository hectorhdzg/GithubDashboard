(function () {
    var THEME_KEY = 'theme';
    var USER_KEY = 'githubUser';

    function setTheme(theme) {
        localStorage.setItem(THEME_KEY, theme);
        document.documentElement.setAttribute('data-theme', theme);
    }

    document.addEventListener('DOMContentLoaded', function () {
        // Theme buttons
        var btnDark = document.getElementById('theme-btn-dark');
        var btnLight = document.getElementById('theme-btn-light');

        if (btnDark) {
            btnDark.addEventListener('click', function () {
                setTheme('dark');
            });
        }
        if (btnLight) {
            btnLight.addEventListener('click', function () {
                setTheme('light');
            });
        }

        // Settings modal
        var input = document.getElementById('settings-github-user');
        var saveBtn = document.getElementById('settings-save');
        var modal = document.getElementById('settingsModal');

        if (input && modal) {
            // Populate input when modal opens
            $(modal).on('show.bs.modal', function () {
                input.value = localStorage.getItem(USER_KEY) || '';
            });

            if (saveBtn) {
                saveBtn.addEventListener('click', function () {
                    var val = (input.value || '').trim().replace(/^@/, '');
                    if (val) {
                        localStorage.setItem(USER_KEY, val);
                    } else {
                        localStorage.removeItem(USER_KEY);
                    }
                    $(modal).modal('hide');
                });
            }
        }
    });
})();
