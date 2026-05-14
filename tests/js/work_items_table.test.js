/**
 * Unit tests for work_items_table.js
 *
 * The production file is an IIFE that registers window.WorkItemsTable.
 * We load it via require() after setting up the DOM fixtures each test needs.
 */

function loadModule() {
  // Reset the module so each test gets a fresh IIFE execution
  jest.resetModules();
  require('../../static/js/work_items_table');
}

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '';
});

// ---------------------------------------------------------------------------
// localStorage helpers (loadFollowed / persistFollowed via toggleFollow)
// ---------------------------------------------------------------------------
describe('localStorage follow helpers', () => {
  test('init works on empty page (no .work-items-table)', () => {
    loadModule();
    expect(window.WorkItemsTable).toBeDefined();
    expect(() => window.WorkItemsTable.init()).not.toThrow();
  });

  test('loadFollowed returns empty array when nothing stored', () => {
    loadModule();
    // We indirectly test via hydrateButtons: no buttons should get active class
    document.body.innerHTML = `
      <div class="work-items-table">
        <table><tbody>
          <tr><td><button class="follow-btn" data-type="issues" data-repo="a/b" data-number="1"><i class="far fa-bookmark"></i></button></td>
              <td data-field="title">Title</td>
              <td data-field="updated" data-value="2025-01-01">2025-01-01</td></tr>
        </tbody></table>
      </div>`;
    window.WorkItemsTable.init();
    expect(document.querySelector('.follow-btn').classList.contains('active')).toBe(false);
  });

  test('legacy migration copies dashboardFavorites to dashboardFollowed', () => {
    const legacy = [{ key: 'issues:a/b:1', repo: 'a/b' }];
    localStorage.setItem('dashboardFavorites', JSON.stringify(legacy));

    document.body.innerHTML = `
      <div class="work-items-table">
        <table><tbody>
          <tr><td><button class="follow-btn" data-type="issues" data-repo="a/b" data-number="1"><i class="far fa-bookmark"></i></button></td>
              <td data-field="title">T</td>
              <td data-field="updated" data-value="">-</td></tr>
        </tbody></table>
      </div>`;
    loadModule();
    window.WorkItemsTable.init();

    // After migration the button should be active
    expect(document.querySelector('.follow-btn').classList.contains('active')).toBe(true);
    // The new key should now exist in storage
    expect(JSON.parse(localStorage.getItem('dashboardFollowed'))).toEqual(legacy);
  });

  test('corrupt localStorage returns empty array gracefully', () => {
    localStorage.setItem('dashboardFollowed', '{{{invalid');
    loadModule();
    document.body.innerHTML = `
      <div class="work-items-table">
        <table><tbody>
          <tr><td><button class="follow-btn" data-type="issues" data-repo="x/y" data-number="5"><i class="far fa-bookmark"></i></button></td>
              <td data-field="title">T</td>
              <td data-field="updated" data-value="">-</td></tr>
        </tbody></table>
      </div>`;
    expect(() => window.WorkItemsTable.init()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// buildKey (tested indirectly through hydrateButtons key matching)
// ---------------------------------------------------------------------------
describe('buildKey', () => {
  test('constructs key from type, repo, number', () => {
    localStorage.setItem(
      'dashboardFollowed',
      JSON.stringify([{ key: 'prs:org/repo:42' }]),
    );

    document.body.innerHTML = `
      <div class="work-items-table">
        <table><tbody>
          <tr><td><button class="follow-btn" data-type="prs" data-repo="org/repo" data-number="42"><i class="far fa-bookmark"></i></button></td>
              <td data-field="title">T</td>
              <td data-field="updated" data-value="">-</td></tr>
        </tbody></table>
      </div>`;
    loadModule();
    window.WorkItemsTable.init();
    expect(document.querySelector('.follow-btn').classList.contains('active')).toBe(true);
  });

  test('defaults type to issues and repo to unknown', () => {
    localStorage.setItem(
      'dashboardFollowed',
      JSON.stringify([{ key: 'issues:unknown:' }]),
    );

    document.body.innerHTML = `
      <div class="work-items-table">
        <table><tbody>
          <tr><td><button class="follow-btn"><i class="far fa-bookmark"></i></button></td>
              <td data-field="title">T</td>
              <td data-field="updated" data-value="">-</td></tr>
        </tbody></table>
      </div>`;
    loadModule();
    window.WorkItemsTable.init();
    expect(document.querySelector('.follow-btn').classList.contains('active')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// toggleFollow (via click events registered by hydrateButtons)
// ---------------------------------------------------------------------------
describe('toggleFollow', () => {
  function setupTable() {
    document.body.innerHTML = `
      <div class="work-items-table">
        <table><tbody>
          <tr><td><button class="follow-btn"
                    data-type="issues" data-repo="org/repo" data-number="7"
                    data-title="My Issue" data-state="open"
                    data-url="https://github.com/org/repo/issues/7"
                    data-updated="2025-06-01" data-created="2025-05-01">
                    <i class="far fa-bookmark"></i></button></td>
              <td data-field="title">My Issue</td>
              <td data-field="updated" data-value="2025-06-01">2025-06-01</td></tr>
        </tbody></table>
      </div>`;
    loadModule();
    window.WorkItemsTable.init();
  }

  test('clicking follow adds item to localStorage', () => {
    setupTable();
    const btn = document.querySelector('.follow-btn');
    btn.click();

    const stored = JSON.parse(localStorage.getItem('dashboardFollowed'));
    expect(stored).toHaveLength(1);
    expect(stored[0].key).toBe('issues:org/repo:7');
    expect(stored[0].title).toBe('My Issue');
    expect(stored[0].repo).toBe('org/repo');
  });

  test('clicking follow marks button as active with solid icon', () => {
    setupTable();
    const btn = document.querySelector('.follow-btn');
    btn.click();
    expect(btn.classList.contains('active')).toBe(true);
    expect(btn.querySelector('i').className).toBe('fas fa-bookmark');
  });

  test('clicking again removes item and restores icon', () => {
    setupTable();
    const btn = document.querySelector('.follow-btn');
    btn.click(); // add
    btn.click(); // remove

    const stored = JSON.parse(localStorage.getItem('dashboardFollowed'));
    expect(stored).toHaveLength(0);
    expect(btn.classList.contains('active')).toBe(false);
    expect(btn.querySelector('i').className).toBe('far fa-bookmark');
  });
});

// ---------------------------------------------------------------------------
// initTable: search, sort, pagination
// ---------------------------------------------------------------------------
function buildTableHTML(rows, pageSize = 2) {
  const trs = rows
    .map(
      (r) => `<tr>
        <td data-field="number" data-value="${r.number}">${r.number}</td>
        <td data-field="title">${r.title}</td>
        <td data-field="labels">${r.labels || ''}</td>
        <td data-field="author">${r.author || ''}</td>
        <td data-field="reviewers">${r.reviewers || ''}</td>
        <td data-field="assignees">${r.assignees || ''}</td>
        <td data-field="state">${r.state || 'open'}</td>
        <td data-field="updated" data-value="${r.updated || ''}">${r.updated || ''}</td>
      </tr>`,
    )
    .join('');

  return `
    <div class="work-items-table" data-page-size="${pageSize}">
      <input type="search" class="work-items-search">
      <table>
        <thead>
          <tr>
            <th class="sortable" data-sort-key="number">#</th>
            <th class="sortable" data-sort-key="title">Title</th>
            <th>Labels</th><th>Author</th><th>Reviewers</th><th>Assignees</th>
            <th class="sortable" data-sort-key="state">State</th>
            <th class="sortable" data-sort-key="updated">Updated</th>
          </tr>
        </thead>
        <tbody>${trs}</tbody>
      </table>
      <span class="work-items-status"></span>
      <span class="work-items-count"></span>
      <button class="work-items-prev">Prev</button>
      <button class="work-items-next">Next</button>
    </div>`;
}

describe('initTable – search', () => {
  test('filters rows by search text (case-insensitive)', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'Fix login bug' },
      { number: 2, title: 'Add feature' },
      { number: 3, title: 'Login error' },
    ], 10);
    loadModule();
    window.WorkItemsTable.init();

    const input = document.querySelector('.work-items-search');
    input.value = 'login';
    input.dispatchEvent(new Event('input'));

    const visible = Array.from(document.querySelectorAll('tbody tr')).filter(
      (r) => r.style.display !== 'none',
    );
    expect(visible).toHaveLength(2);
  });

  test('empty search shows all rows', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
    ], 10);
    loadModule();
    window.WorkItemsTable.init();

    const input = document.querySelector('.work-items-search');
    input.value = 'xyz';
    input.dispatchEvent(new Event('input'));
    input.value = '';
    input.dispatchEvent(new Event('input'));

    const visible = Array.from(document.querySelectorAll('tbody tr')).filter(
      (r) => r.style.display !== 'none',
    );
    expect(visible).toHaveLength(2);
  });

  test('status shows "No results" when nothing matches', () => {
    document.body.innerHTML = buildTableHTML([{ number: 1, title: 'Hello' }], 10);
    loadModule();
    window.WorkItemsTable.init();

    const input = document.querySelector('.work-items-search');
    input.value = 'zzzzzzz';
    input.dispatchEvent(new Event('input'));

    expect(document.querySelector('.work-items-status').textContent).toBe('No results');
  });
});

describe('initTable – sorting', () => {
  test('clicking number header sorts ascending then toggles', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 3, title: 'C' },
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
    ], 10);
    loadModule();
    window.WorkItemsTable.init();

    const numberHeader = document.querySelector('[data-sort-key="number"]');
    numberHeader.click();

    const nums = Array.from(document.querySelectorAll('tbody tr')).map(
      (r) => r.querySelector('[data-field="number"]').dataset.value,
    );
    expect(nums).toEqual(['1', '2', '3']);
    expect(numberHeader.classList.contains('active-asc')).toBe(true);

    // Click again toggles to desc
    numberHeader.click();
    const numsDesc = Array.from(document.querySelectorAll('tbody tr')).map(
      (r) => r.querySelector('[data-field="number"]').dataset.value,
    );
    expect(numsDesc).toEqual(['3', '2', '1']);
    expect(numberHeader.classList.contains('active-desc')).toBe(true);
  });

  test('clicking title header sorts desc by default', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'Alpha' },
      { number: 2, title: 'Charlie' },
      { number: 3, title: 'Bravo' },
    ], 10);
    loadModule();
    window.WorkItemsTable.init();

    document.querySelector('[data-sort-key="title"]').click();
    const titles = Array.from(document.querySelectorAll('tbody tr')).map(
      (r) => r.querySelector('[data-field="title"]').textContent,
    );
    expect(titles).toEqual(['Charlie', 'Bravo', 'Alpha']);
  });
});

describe('initTable – pagination', () => {
  test('paginates rows according to data-page-size', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
      { number: 3, title: 'C' },
    ], 2);
    loadModule();
    window.WorkItemsTable.init();

    const visible = Array.from(document.querySelectorAll('tbody tr')).filter(
      (r) => r.style.display !== 'none',
    );
    expect(visible).toHaveLength(2);
    expect(document.querySelector('.work-items-prev').disabled).toBe(true);
    expect(document.querySelector('.work-items-next').disabled).toBe(false);
  });

  test('next button advances to next page', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
      { number: 3, title: 'C' },
    ], 2);
    loadModule();
    window.WorkItemsTable.init();

    document.querySelector('.work-items-next').click();
    const visible = Array.from(document.querySelectorAll('tbody tr')).filter(
      (r) => r.style.display !== 'none',
    );
    expect(visible).toHaveLength(1);
    expect(document.querySelector('.work-items-prev').disabled).toBe(false);
    expect(document.querySelector('.work-items-next').disabled).toBe(true);
  });

  test('prev button goes back', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
      { number: 3, title: 'C' },
    ], 2);
    loadModule();
    window.WorkItemsTable.init();

    document.querySelector('.work-items-next').click();
    document.querySelector('.work-items-prev').click();

    expect(document.querySelector('.work-items-prev').disabled).toBe(true);
  });

  test('count element shows total items', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
    ], 10);
    loadModule();
    window.WorkItemsTable.init();

    expect(document.querySelector('.work-items-count').textContent).toBe('2 items');
  });

  test('count element uses singular for 1 item', () => {
    document.body.innerHTML = buildTableHTML([{ number: 1, title: 'Only' }], 10);
    loadModule();
    window.WorkItemsTable.init();

    expect(document.querySelector('.work-items-count').textContent).toBe('1 item');
  });

  test('status shows range text', () => {
    document.body.innerHTML = buildTableHTML([
      { number: 1, title: 'A' },
      { number: 2, title: 'B' },
      { number: 3, title: 'C' },
    ], 2);
    loadModule();
    window.WorkItemsTable.init();

    expect(document.querySelector('.work-items-status').textContent).toBe('1-2 of 3');
  });
});
