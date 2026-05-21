(function () {
    const STORAGE_KEY = 'dashboardFollowed';
    const LEGACY_KEY = 'dashboardFavorites';
    const container = document.getElementById('followed-container');
    const clearButton = document.getElementById('clear-followed');

    if (!container) {
        return;
    }

    function migrateLegacyIfNeeded(current) {
        if (Array.isArray(current) && current.length > 0) {
            return current;
        }
        try {
            const legacyRaw = window.localStorage.getItem(LEGACY_KEY) || '[]';
            const legacy = JSON.parse(legacyRaw);
            if (Array.isArray(legacy) && legacy.length > 0) {
                window.localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));
                return legacy;
            }
        } catch (error) {
            console.warn('followed.js: unable to migrate legacy favorites', error);
        }
        return current;
    }

    function loadFollowed() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY) || '[]';
            const parsed = migrateLegacyIfNeeded(JSON.parse(raw));
            if (!Array.isArray(parsed) || parsed.length === 0) {
                renderEmptyState();
                return;
            }
            renderTable(parsed);
        } catch (error) {
            container.innerHTML = '<div class="alert alert-danger">Unable to read followed items from local storage.</div>';
            console.warn('followed.js: unable to parse followed items from storage', error);
        }
    }

    function renderEmptyState() {
        container.innerHTML = '<div class="alert alert-info mb-0">No followed items yet. Visit a repository page and click the follow button to add one.</div>';
    }

    function renderTable(items) {
        const sorted = items.sort((a, b) => (b.updatedAt || '').localeCompare(a.updatedAt || ''));
        const rows = sorted
            .map((item) => {
                const url = item.url || (item.repo ? `https://github.com/${item.repo}/${item.dataType === 'prs' ? 'pull' : 'issues'}/${item.number}` : '#');
                const repoUrl = item.repo ? `https://github.com/${item.repo}` : '#';
                const updated = item.updatedAt || item.createdAt || '';
                const typeLabel = item.dataType === 'prs' ? 'Pull Request' : 'Issue';
                return `
                    <tr>
                        <td class="follow-cell">
                            <button class="follow-btn active" title="Unfollow"
                                data-repo="${item.repo || ''}"
                                data-repo-display="${escapeHtml(item.repoDisplay || item.repo || '')}"
                                data-number="${item.number || ''}"
                                data-title="${escapeHtml(item.title || '')}"
                                data-type="${item.dataType || 'issues'}"
                                data-state="${item.state || ''}"
                                data-url="${url}"
                                data-updated="${item.updatedAt || ''}"
                                data-created="${item.createdAt || ''}">
                            </button>
                        </td>
                        <td data-field="number" data-value="${item.number || 0}"><a href="${url}" target="_blank">#${item.number}</a></td>
                        <td class="align-middle title-cell" data-field="title">
                            <a href="${url}" target="_blank">${escapeHtml(item.title || 'Untitled')}</a>
                            <div class="text-muted small">${escapeHtml(item.repoDisplay || item.repo || '')}</div>
                        </td>
                        <td class="align-middle text-nowrap text-capitalize" data-field="state">${escapeHtml(item.state || 'unknown')}</td>
                        <td class="align-middle" data-field="labels"><span class="badge badge-pill badge-secondary">${typeLabel}</span></td>
                        <td class="align-middle" data-field="author"><a href="${repoUrl}" target="_blank">${escapeHtml(item.repo || '')}</a></td>
                        <td class="align-middle" data-field="assignees">${escapeHtml(item.repoDisplay || '')}</td>
                        <td class="align-middle text-nowrap" data-field="updated" data-value="${updated}">${updated || '—'}</td>
                    </tr>
                `;
            })
            .join('');

        container.innerHTML = `
            <div class="work-items-table" data-page-size="10">
                <div class="table-responsive work-items-table-wrapper">
                    <table class="table table-striped table-hover align-middle">
                        <thead class="thead-light">
                            <tr>
                                <th scope="col" class="text-nowrap follow-cell">Follow</th>
                                <th scope="col" class="text-nowrap sortable" data-sort-key="number">#</th>
                                <th scope="col" class="sortable" data-sort-key="title" style="min-width: 260px;">Title</th>
                                <th scope="col" class="sortable" data-sort-key="state">State</th>
                                <th scope="col" class="sortable" data-sort-key="labels" style="min-width: 180px;">Labels</th>
                                <th scope="col" class="sortable" data-sort-key="author">Repository</th>
                                <th scope="col" class="sortable" data-sort-key="assignees" style="min-width: 160px;">Display</th>
                                <th scope="col" class="sortable" data-sort-key="updated">Updated</th>
                            </tr>
                            <tr class="work-items-filters">
                                <th></th>
                                <th></th>
                                <th colspan="6" class="p-1">
                                    <div class="input-group input-group-sm work-items-search-group">
                                    <input type="search" class="form-control work-items-search" placeholder="Search title, repo, state...">
                                    </div>
                                </th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                        <tfoot>
                            <tr>
                                <td colspan="8" class="p-2">
                                    <div class="work-items-pagination">
                                        <div class="d-flex flex-column flex-md-row align-items-md-center justify-content-md-between">
                                            <div class="work-items-status small text-muted mb-2 mb-md-0"></div>
                                            <div class="btn-group btn-group-sm" role="group">
                                                <button class="btn btn-outline-secondary work-items-prev" type="button">Previous</button>
                                                <button class="btn btn-outline-secondary work-items-next" type="button">Next</button>
                                            </div>
                                        </div>
                                    </div>
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </div>
        `;

        // Allow unfollow to remove from the list and rerender
        container.querySelectorAll('.follow-btn').forEach((button) => {
            button.addEventListener('click', () => {
                removeFollowed(button.dataset.type + ':' + button.dataset.repo + ':' + button.dataset.number);
            });
        });

        if (window.WorkItemsTable && typeof window.WorkItemsTable.init === 'function') {
            window.WorkItemsTable.init();
        }
    }

    function removeFollowed(key) {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY) || '[]';
            const parsed = JSON.parse(raw);
            const next = parsed.filter((entry) => entry && entry.key !== key);
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
            loadFollowed();
        } catch (error) {
            console.warn('followed.js: unable to remove followed item', error);
        }
    }

    function clearFollowed() {
        window.localStorage.removeItem(STORAGE_KEY);
        loadFollowed();
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    if (clearButton) {
        clearButton.addEventListener('click', clearFollowed);
    }

    loadFollowed();
})();
