// Reusable work items table behavior (follow/unfollow, search, sort, pagination)
(function () {
    const KEY = 'dashboardFollowed';
    const LEGACY_KEY = 'dashboardFavorites';

    function loadFollowed() {
        try {
            const raw = window.localStorage.getItem(KEY);
            const parsed = raw ? JSON.parse(raw) : null;
            if (Array.isArray(parsed)) {
                return parsed;
            }

            // Legacy migration
            const legacyRaw = window.localStorage.getItem(LEGACY_KEY) || '[]';
            const legacyParsed = JSON.parse(legacyRaw);
            if (Array.isArray(legacyParsed)) {
                window.localStorage.setItem(KEY, JSON.stringify(legacyParsed));
                return legacyParsed;
            }
            return [];
        } catch (e) {
            console.warn('Unable to load followed items', e);
            return [];
        }
    }

    function persistFollowed(list) {
        try {
            window.localStorage.setItem(KEY, JSON.stringify(list));
        } catch (e) {
            console.warn('Unable to persist followed items', e);
        }
    }

    function buildKey(type, repo, number) {
        return `${type || 'issues'}:${repo || 'unknown'}:${number || ''}`;
    }

    function toggleFollow(button) {
        const repo = button.dataset.repo || '';
        const repoDisplay = button.dataset.repoDisplay || repo;
        const number = button.dataset.number || '';
        const title = button.dataset.title || '';
        const type = button.dataset.type || 'issues';
        const state = button.dataset.state || '';
        const url = button.dataset.url || '';
        const updatedAt = button.dataset.updated || '';
        const createdAt = button.dataset.created || '';

        const key = buildKey(type, repo, number);
        const list = loadFollowed();
        const idx = list.findIndex((item) => item && item.key === key);

        if (idx >= 0) {
            list.splice(idx, 1);
            button.classList.remove('active');
            button.querySelector('i').className = 'far fa-bookmark';
        } else {
            list.push({ key, dataType: type, repo, repoDisplay, number, title, state, url, updatedAt, createdAt });
            button.classList.add('active');
            button.querySelector('i').className = 'fas fa-bookmark';
        }

        persistFollowed(list);
    }

    function hydrateButtons(container) {
        const list = loadFollowed();
        const set = new Set(list.map((item) => item.key));
        container.querySelectorAll('.follow-btn').forEach((btn) => {
            const key = buildKey(btn.dataset.type, btn.dataset.repo, btn.dataset.number);
            if (set.has(key)) {
                btn.classList.add('active');
                btn.querySelector('i').className = 'fas fa-bookmark';
            }
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                toggleFollow(btn);
            });
        });
    }

    function parseDate(value) {
        const ts = Date.parse(value || '');
        return Number.isFinite(ts) ? ts : 0;
    }

    function initTable(container) {
        const table = container.querySelector('table');
        const tbody = table.querySelector('tbody');
        const searchInput = container.querySelector('.work-items-search');
        const statusEl = container.querySelector('.work-items-status');
        const countEl = container.querySelector('.work-items-count');
        const prevBtn = container.querySelector('.work-items-prev');
        const nextBtn = container.querySelector('.work-items-next');
        const sortHeaders = container.querySelectorAll('.sortable');
        const pageSize = parseInt(container.dataset.pageSize, 10) || 10;

        const items = Array.from(tbody.querySelectorAll('tr')).map((row) => {
            const getText = (field) => (row.querySelector(`[data-field="${field}"]`) || {}).textContent?.trim() || '';
            const getValue = (field) => (row.querySelector(`[data-field="${field}"]`) || {}).dataset?.value || '';
            const title = getText('title');
            const labels = getText('labels');
            const author = getText('author');
            const reviewers = getText('reviewers');
            const assignees = getText('assignees');
            const state = getText('state');
            const updatedRaw = getValue('updated') || getText('updated');
            return {
                row,
                number: parseInt(getValue('number') || '0', 10) || 0,
                title,
                labels,
                author,
                reviewers,
                assignees,
                state,
                updated: updatedRaw,
                updatedTs: parseDate(updatedRaw),
                searchText: `${title} ${labels} ${author} ${reviewers} ${assignees} ${state}`.toLowerCase(),
            };
        });

        let searchQuery = '';
        let sortKey = 'updated';
        let sortDir = 'desc';
        let page = 1;

        function applySort(list) {
            const key = sortKey;
            const dir = sortDir === 'desc' ? -1 : 1;
            return list.sort((a, b) => {
                let va = a[key];
                let vb = b[key];
                if (key === 'number') {
                    return (va - vb) * dir;
                }
                if (key === 'updated') {
                    return (a.updatedTs - b.updatedTs) * dir;
                }
                va = (va || '').toString().toLowerCase();
                vb = (vb || '').toString().toLowerCase();
                if (va === vb) return 0;
                return va > vb ? dir : -dir;
            });
        }

        function refresh() {
            const filtered = items.filter((item) => item.searchText.includes(searchQuery));
            applySort(filtered);

            const total = filtered.length;
            const pageCount = Math.max(1, Math.ceil(total / pageSize));
            page = Math.min(Math.max(page, 1), pageCount);
            const start = (page - 1) * pageSize;
            const end = Math.min(start + pageSize, total);

            const frag = document.createDocumentFragment();
            filtered.forEach((item, idx) => {
                item.row.style.display = idx >= start && idx < end ? '' : 'none';
                frag.appendChild(item.row);
            });
            tbody.innerHTML = '';
            tbody.appendChild(frag);

            if (countEl) {
                countEl.textContent = `${total} item${total === 1 ? '' : 's'}`;
            }
            if (statusEl) {
                statusEl.textContent = total === 0 ? 'No results' : `${start + 1}-${end} of ${total}`;
            }
            if (prevBtn) prevBtn.disabled = page <= 1;
            if (nextBtn) nextBtn.disabled = page >= pageCount;
        }

        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                searchQuery = (e.target.value || '').toLowerCase();
                page = 1;
                refresh();
            });
        }

        sortHeaders.forEach((th) => {
            th.addEventListener('click', () => {
                const key = th.dataset.sortKey;
                if (!key) return;
                if (sortKey === key) {
                    sortDir = sortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    sortKey = key;
                    sortDir = key === 'number' ? 'asc' : 'desc';
                }
                sortHeaders.forEach((el) => el.classList.remove('active-asc', 'active-desc'));
                th.classList.add(sortDir === 'asc' ? 'active-asc' : 'active-desc');
                page = 1;
                refresh();
            });
        });

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                page = Math.max(1, page - 1);
                refresh();
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                page += 1;
                refresh();
            });
        }

        refresh();
    }

    window.WorkItemsTable = {
        init() {
            const tables = document.querySelectorAll('.work-items-table');
            tables.forEach((container) => {
                hydrateButtons(container);
                initTable(container);
            });
        },
    };
})();
