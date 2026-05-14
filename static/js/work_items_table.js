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

    function timeAgo(dateStr) {
        const ts = Date.parse(dateStr || '');
        if (!Number.isFinite(ts)) return dateStr || '';
        const seconds = Math.floor((Date.now() - ts) / 1000);
        if (seconds < 60) return 'just now';
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return minutes + 'm ago';
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return hours + 'h ago';
        const days = Math.floor(hours / 24);
        if (days < 30) return days + 'd ago';
        const months = Math.floor(days / 30);
        if (months < 12) return months + 'mo ago';
        const years = Math.floor(months / 12);
        return years + 'y ago';
    }

    function applyAgeAndStale(container) {
        const now = Date.now();
        const DAY = 86400000;
        container.querySelectorAll('.age-text[data-timestamp]').forEach((el) => {
            const raw = el.dataset.timestamp;
            const ts = Date.parse(raw || '');
            if (!Number.isFinite(ts)) return;
            el.textContent = timeAgo(raw);
            el.title = raw;
            // Stale highlighting on the row
            const row = el.closest('tr');
            if (!row) return;
            const ageDays = (now - ts) / DAY;
            if (ageDays > 90) {
                row.setAttribute('data-stale', 'danger');
                el.insertAdjacentHTML('afterend', ' <span class="stale-badge stale-badge--danger">90d+</span>');
            } else if (ageDays > 30) {
                row.setAttribute('data-stale', 'warning');
                el.insertAdjacentHTML('afterend', ' <span class="stale-badge stale-badge--warning">30d+</span>');
            }
        });
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
        const filterSelects = container.querySelectorAll('.work-items-filter');
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

        // Restore state from URL query params
        const urlParams = new URLSearchParams(window.location.search);
        let searchQuery = urlParams.get('q') || '';
        let sortKey = urlParams.get('sort') || 'updated';
        let sortDir = urlParams.get('dir') || 'desc';
        let page = parseInt(urlParams.get('page'), 10) || 1;
        const activeFilters = {};

        // Pre-fill search input from URL
        if (searchInput && searchQuery) {
            searchInput.value = searchQuery;
            searchQuery = searchQuery.toLowerCase();
        }

        // Pre-fill filter dropdowns from URL
        filterSelects.forEach((select) => {
            const field = select.dataset.filterField;
            if (!field) return;
            const urlVal = urlParams.get('f_' + field);
            if (urlVal) {
                activeFilters[field] = urlVal;
            }
        });

        // Pre-activate sort header from URL
        if (sortKey !== 'updated' || sortDir !== 'desc') {
            sortHeaders.forEach((th) => {
                if (th.dataset.sortKey === sortKey) {
                    th.classList.add(sortDir === 'asc' ? 'active-asc' : 'active-desc');
                }
            });
        }

        function syncUrl() {
            // Only sync if we're on the dashboard page with a repo selected
            if (!urlParams.has('repo')) return;
            const u = new URLSearchParams(window.location.search);
            // Preserve server-side params
            const keep = ['repo', 'type', 'state'];
            const newParams = new URLSearchParams();
            keep.forEach((k) => { if (u.has(k)) newParams.set(k, u.get(k)); });
            if (searchQuery) newParams.set('q', searchQuery);
            if (sortKey !== 'updated') newParams.set('sort', sortKey);
            if (sortDir !== 'desc') newParams.set('dir', sortDir);
            if (page > 1) newParams.set('page', page);
            for (const field in activeFilters) {
                if (activeFilters[field]) newParams.set('f_' + field, activeFilters[field]);
            }
            const qs = newParams.toString();
            const newUrl = window.location.pathname + (qs ? '?' + qs : '');
            window.history.replaceState(null, '', newUrl);
        }

        // Populate filter dropdowns with unique values from the data
        filterSelects.forEach((select) => {
            const field = select.dataset.filterField;
            if (!field) return;
            const valuesSet = new Set();
            items.forEach((item) => {
                const text = (item[field] || '').trim();
                // Labels / users may be comma-or-space separated tokens
                text.split(/[,\n]+/).forEach((tok) => {
                    const v = tok.replace(/^@/, '').trim();
                    if (v && v !== 'None') valuesSet.add(v);
                });
            });
            Array.from(valuesSet).sort((a, b) => a.localeCompare(b)).forEach((v) => {
                const opt = document.createElement('option');
                opt.value = v.toLowerCase();
                opt.textContent = v;
                select.appendChild(opt);
            });
            select.addEventListener('change', () => {
                activeFilters[field] = select.value;
                page = 1;
                refresh();
                syncUrl();
            });
            // Set dropdown value from URL
            const urlVal = urlParams.get('f_' + field);
            if (urlVal) select.value = urlVal;
        });

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
            const filtered = items.filter((item) => {
                if (searchQuery && !item.searchText.includes(searchQuery)) return false;
                for (const field in activeFilters) {
                    const filterVal = activeFilters[field];
                    if (!filterVal) continue;
                    const cellText = (item[field] || '').toLowerCase();
                    if (!cellText.includes(filterVal)) return false;
                }
                return true;
            });
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
                syncUrl();
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
                syncUrl();
            });
        });

        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                page = Math.max(1, page - 1);
                refresh();
                syncUrl();
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                page += 1;
                refresh();
                syncUrl();
            });
        }

        refresh();
    }

    function initRowModals(container) {
        const rows = container.querySelectorAll('.work-item-row');
        rows.forEach((row) => {
            row.addEventListener('click', (e) => {
                // Don't open modal if clicking a link, button, or input
                if (e.target.closest('a, button, input, select')) return;

                const data = row.dataset;
                const modal = document.getElementById('workItemModal');
                if (!modal) return;

                // Title
                const typeIcon = data.itemType === 'prs' ? '<i class="fas fa-code-branch mr-2"></i>' : '<i class="fas fa-dot-circle mr-2"></i>';
                modal.querySelector('#modal-type-icon').innerHTML = typeIcon;
                modal.querySelector('#modal-title-text').textContent = data.itemTitle || 'Untitled';

                // Number
                modal.querySelector('#modal-number').textContent = '#' + (data.itemNumber || '');

                // State badge
                const stateBadge = modal.querySelector('#modal-state-badge');
                const state = (data.itemState || '').toLowerCase();
                if (data.itemType === 'prs') {
                    if (data.itemMerged) {
                        stateBadge.className = 'badge badge-pr-merged';
                        stateBadge.innerHTML = '<i class="fas fa-code-merge mr-1"></i>Merged';
                    } else if (data.itemDraft === 'True') {
                        stateBadge.className = 'badge badge-pr-draft';
                        stateBadge.innerHTML = '<i class="fas fa-pencil-alt mr-1"></i>Draft';
                    } else if (state === 'open') {
                        stateBadge.className = 'badge badge-pr-open';
                        stateBadge.innerHTML = '<i class="fas fa-code-branch mr-1"></i>Open';
                    } else {
                        stateBadge.className = 'badge badge-pr-closed';
                        stateBadge.innerHTML = '<i class="fas fa-times-circle mr-1"></i>Closed';
                    }
                } else {
                    if (state === 'open') {
                        stateBadge.className = 'badge badge-success';
                        stateBadge.textContent = 'Open';
                    } else {
                        stateBadge.className = 'badge badge-danger';
                        stateBadge.textContent = 'Closed';
                    }
                }

                // Repo
                const repoLink = modal.querySelector('#modal-repo-link');
                repoLink.textContent = data.itemRepoDisplay || data.itemRepo || '';
                repoLink.href = data.itemRepo ? 'https://github.com/' + data.itemRepo : '#';

                // Author
                const authorLink = modal.querySelector('#modal-author-link');
                const author = data.itemAuthor || '';
                if (author) {
                    authorLink.innerHTML = '<img class="avatar-sm" src="https://github.com/' + author + '.png?size=40" alt="">@' + author;
                    authorLink.href = 'https://github.com/' + author;
                    authorLink.style.display = '';
                } else {
                    authorLink.textContent = 'Unknown';
                    authorLink.href = '#';
                }

                // Dates
                const created = data.itemCreated || '';
                const updated = data.itemUpdated || '';
                modal.querySelector('#modal-created').textContent = created ? timeAgo(created) : '—';
                modal.querySelector('#modal-created').title = created;
                modal.querySelector('#modal-updated').textContent = updated ? timeAgo(updated) : '—';
                modal.querySelector('#modal-updated').title = updated;

                // Labels (grab from the row's labels cell)
                const labelsCell = row.querySelector('[data-field="labels"]');
                const labelsSection = modal.querySelector('#modal-labels-section');
                const labelsContainer = modal.querySelector('#modal-labels');
                if (labelsCell && labelsCell.textContent.trim() && labelsCell.textContent.trim() !== 'None') {
                    labelsContainer.innerHTML = labelsCell.innerHTML;
                    labelsSection.style.display = '';
                } else {
                    labelsSection.style.display = 'none';
                }

                // Body / description
                const bodySection = modal.querySelector('#modal-body-section');
                const bodyContent = modal.querySelector('#modal-body-content');
                if (data.itemBody) {
                    bodyContent.textContent = data.itemBody;
                    bodySection.style.display = '';
                } else {
                    bodySection.style.display = 'none';
                }

                // GitHub link
                modal.querySelector('#modal-github-link').href = data.itemUrl || '#';

                // Show the modal (Bootstrap 4)
                if (window.$ && window.$.fn.modal) {
                    $(modal).modal('show');
                } else {
                    modal.classList.add('show');
                    modal.style.display = 'block';
                    modal.setAttribute('aria-hidden', 'false');
                    // Simple backdrop
                    let backdrop = document.querySelector('.modal-backdrop');
                    if (!backdrop) {
                        backdrop = document.createElement('div');
                        backdrop.className = 'modal-backdrop fade show';
                        document.body.appendChild(backdrop);
                    }
                    document.body.classList.add('modal-open');
                    // Close handlers
                    const closeModal = () => {
                        modal.classList.remove('show');
                        modal.style.display = 'none';
                        modal.setAttribute('aria-hidden', 'true');
                        document.body.classList.remove('modal-open');
                        if (backdrop && backdrop.parentNode) backdrop.parentNode.removeChild(backdrop);
                    };
                    modal.querySelectorAll('[data-dismiss="modal"]').forEach((btn) => {
                        btn.addEventListener('click', closeModal, { once: true });
                    });
                    backdrop.addEventListener('click', closeModal, { once: true });
                }
            });
        });
    }

    window.WorkItemsTable = {
        init() {
            const tables = document.querySelectorAll('.work-items-table');
            tables.forEach((container) => {
                applyAgeAndStale(container);
                hydrateButtons(container);
                initTable(container);
                initRowModals(container);
            });
        },
    };
})();
