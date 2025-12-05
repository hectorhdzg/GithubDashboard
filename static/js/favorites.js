(function () {
    const STORAGE_KEY = 'dashboardFavorites';
    const container = document.getElementById('favorites-container');
    const clearButton = document.getElementById('clear-favorites');

    if (!container) {
        return;
    }

    function loadFavorites() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY) || '[]';
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed) || parsed.length === 0) {
                renderEmptyState();
                return;
            }
            renderTable(parsed);
        } catch (error) {
            container.innerHTML = '<div class="alert alert-danger">Unable to read favorites from local storage.</div>';
            console.warn('favorites.js: unable to parse favorites from storage', error);
        }
    }

    function renderEmptyState() {
        container.innerHTML = '<div class="alert alert-info mb-0">No favorites found. Visit a repository page and click the star to add one.</div>';
    }

    function renderTable(favorites) {
        const rows = favorites
            .sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''))
            .map((fav) => {
                const url = fav.url || (fav.repo ? `https://github.com/${fav.repo}/${fav.dataType === 'prs' ? 'pull' : 'issues'}/${fav.number}` : '#');
                const repoUrl = fav.repo ? `https://github.com/${fav.repo}` : '#';
                return `
                    <tr>
                        <td style="width: 70px;" class="text-center">
                            <button class="btn btn-sm btn-outline-warning" data-favorite-key="${fav.key}">
                                <i class="fas fa-star"></i>
                            </button>
                        </td>
                        <td style="width: 120px;">${fav.dataType === 'prs' ? 'Pull Request' : 'Issue'}</td>
                        <td style="width: 90px;"><a href="${url}" target="_blank">#${fav.number}</a></td>
                        <td><a href="${url}" target="_blank">${escapeHtml(fav.title || 'Untitled')}</a></td>
                        <td style="width: 220px;"><a href="${repoUrl}" target="_blank">${escapeHtml(fav.repoDisplay || fav.repo || '')}</a></td>
                        <td style="width: 110px;" class="text-capitalize">${fav.state || 'unknown'}</td>
                        <td style="width: 160px;">${fav.updatedAt || fav.createdAt || '—'}</td>
                    </tr>
                `;
            })
            .join('');

        container.innerHTML = `
            <div class="table-responsive">
                <table class="table table-sm table-hover">
                    <thead class="thead-light">
                        <tr>
                            <th class="text-center" style="width: 70px;">Unpin</th>
                            <th style="width: 120px;">Type</th>
                            <th style="width: 90px;">#</th>
                            <th>Title</th>
                            <th style="width: 220px;">Repository</th>
                            <th style="width: 110px;">State</th>
                            <th style="width: 160px;">Updated</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;

        container.querySelectorAll('button[data-favorite-key]').forEach((button) => {
            button.addEventListener('click', () => {
                removeFavorite(button.getAttribute('data-favorite-key'));
            });
        });
    }

    function removeFavorite(key) {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY) || '[]';
            const parsed = JSON.parse(raw);
            const next = parsed.filter((entry) => entry && entry.key !== key);
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
            loadFavorites();
        } catch (error) {
            console.warn('favorites.js: unable to remove favorite', error);
        }
    }

    function clearFavorites() {
        window.localStorage.removeItem(STORAGE_KEY);
        loadFavorites();
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    if (clearButton) {
        clearButton.addEventListener('click', clearFavorites);
    }

    loadFavorites();
})();
