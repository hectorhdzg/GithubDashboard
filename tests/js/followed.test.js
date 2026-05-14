/**
 * Unit tests for followed.js
 *
 * The module is an IIFE that auto-runs on load, looking for #followed-container.
 * We set up the DOM before requiring the module each time.
 */

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '';
  // Provide a stub WorkItemsTable so renderTable can call init()
  window.WorkItemsTable = { init: jest.fn() };
});

function loadModule() {
  jest.resetModules();
  require('../../static/js/followed.js');
}

// ---------------------------------------------------------------------------
// escapeHtml (tested indirectly through rendered output)
// ---------------------------------------------------------------------------
describe('escapeHtml', () => {
  test('escapes HTML special characters in titles', () => {
    const item = {
      key: 'issues:a/b:1',
      dataType: 'issues',
      repo: 'a/b',
      number: 1,
      title: '<script>alert("xss")</script>',
      state: 'open',
    };
    localStorage.setItem('dashboardFollowed', JSON.stringify([item]));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    const container = document.getElementById('followed-container');
    // Verify no actual <script> element was created (XSS prevention)
    expect(container.querySelectorAll('script')).toHaveLength(0);
    // Verify title text content is escaped, not rendered as HTML
    const titleLink = container.querySelector('.title-cell a');
    expect(titleLink.textContent).toContain('<script>');
    expect(titleLink.textContent).not.toBe('');
  });

  test('handles null values without crashing', () => {
    const item = {
      key: 'issues:a/b:2',
      dataType: 'issues',
      repo: 'a/b',
      number: 2,
      title: null,
      state: null,
    };
    localStorage.setItem('dashboardFollowed', JSON.stringify([item]));
    document.body.innerHTML = '<div id="followed-container"></div>';
    expect(() => loadModule()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// migrateLegacyIfNeeded
// ---------------------------------------------------------------------------
describe('migrateLegacyIfNeeded', () => {
  test('migrates dashboardFavorites to dashboardFollowed when followed is empty', () => {
    const legacy = [{ key: 'issues:x/y:5', repo: 'x/y', number: 5, title: 'Legacy' }];
    localStorage.setItem('dashboardFavorites', JSON.stringify(legacy));

    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    // Should have migrated
    const stored = JSON.parse(localStorage.getItem('dashboardFollowed'));
    expect(stored).toEqual(legacy);

    // Should render the item
    expect(document.getElementById('followed-container').innerHTML).toContain('Legacy');
  });

  test('does not overwrite existing followed items', () => {
    const current = [{ key: 'issues:a/b:1', repo: 'a/b', number: 1, title: 'Current' }];
    const legacy = [{ key: 'issues:x/y:5', repo: 'x/y', number: 5, title: 'Legacy' }];
    localStorage.setItem('dashboardFollowed', JSON.stringify(current));
    localStorage.setItem('dashboardFavorites', JSON.stringify(legacy));

    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    const container = document.getElementById('followed-container');
    expect(container.innerHTML).toContain('Current');
    expect(container.innerHTML).not.toContain('Legacy');
  });
});

// ---------------------------------------------------------------------------
// renderEmptyState
// ---------------------------------------------------------------------------
describe('renderEmptyState', () => {
  test('shows info message when no followed items', () => {
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    const container = document.getElementById('followed-container');
    expect(container.innerHTML).toContain('No followed items yet');
    expect(container.innerHTML).toContain('alert-info');
  });

  test('shows info message for empty array', () => {
    localStorage.setItem('dashboardFollowed', '[]');
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    expect(document.getElementById('followed-container').innerHTML).toContain('No followed items yet');
  });
});

// ---------------------------------------------------------------------------
// renderTable
// ---------------------------------------------------------------------------
describe('renderTable', () => {
  const sampleItems = [
    {
      key: 'issues:org/repo:10',
      dataType: 'issues',
      repo: 'org/repo',
      repoDisplay: 'My Repo',
      number: 10,
      title: 'Test Issue',
      state: 'open',
      url: 'https://github.com/org/repo/issues/10',
      updatedAt: '2025-06-01',
      createdAt: '2025-05-01',
    },
  ];

  test('renders a table with the item', () => {
    localStorage.setItem('dashboardFollowed', JSON.stringify(sampleItems));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    const container = document.getElementById('followed-container');
    expect(container.querySelector('table')).not.toBeNull();
    expect(container.innerHTML).toContain('Test Issue');
    expect(container.innerHTML).toContain('#10');
  });

  test('generates correct GitHub URL for issues', () => {
    const items = [{ ...sampleItems[0], url: '' }];
    localStorage.setItem('dashboardFollowed', JSON.stringify(items));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    expect(document.getElementById('followed-container').innerHTML).toContain(
      'https://github.com/org/repo/issues/10',
    );
  });

  test('generates correct GitHub URL for pull requests', () => {
    const items = [{ ...sampleItems[0], dataType: 'prs', url: '', number: 20 }];
    localStorage.setItem('dashboardFollowed', JSON.stringify(items));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    expect(document.getElementById('followed-container').innerHTML).toContain(
      'https://github.com/org/repo/pull/20',
    );
  });

  test('shows type badge (Issue vs Pull Request)', () => {
    localStorage.setItem('dashboardFollowed', JSON.stringify(sampleItems));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    expect(document.getElementById('followed-container').innerHTML).toContain('Issue');
  });

  test('calls WorkItemsTable.init after rendering', () => {
    localStorage.setItem('dashboardFollowed', JSON.stringify(sampleItems));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    expect(window.WorkItemsTable.init).toHaveBeenCalled();
  });

  test('sorts items by updatedAt descending', () => {
    const items = [
      { ...sampleItems[0], key: 'issues:a:1', number: 1, title: 'Older', updatedAt: '2025-01-01' },
      { ...sampleItems[0], key: 'issues:a:2', number: 2, title: 'Newer', updatedAt: '2025-06-01' },
    ];
    localStorage.setItem('dashboardFollowed', JSON.stringify(items));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    const titles = Array.from(
      document.querySelectorAll('[data-field="title"]'),
    ).map((el) => el.textContent.trim());

    // "Newer" (2025-06-01) should come first
    expect(titles[0]).toContain('Newer');
  });
});

// ---------------------------------------------------------------------------
// removeFollowed
// ---------------------------------------------------------------------------
describe('removeFollowed', () => {
  test('clicking unfollow button removes item and re-renders', () => {
    const items = [
      { key: 'issues:org/repo:10', dataType: 'issues', repo: 'org/repo', number: 10, title: 'Item A', state: 'open' },
      { key: 'issues:org/repo:20', dataType: 'issues', repo: 'org/repo', number: 20, title: 'Item B', state: 'open' },
    ];
    localStorage.setItem('dashboardFollowed', JSON.stringify(items));
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    // Click the first unfollow button
    const buttons = document.querySelectorAll('.follow-btn');
    expect(buttons.length).toBe(2);
    buttons[0].click();

    // Should now only have one item in storage
    const stored = JSON.parse(localStorage.getItem('dashboardFollowed'));
    expect(stored).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// clearFollowed
// ---------------------------------------------------------------------------
describe('clearFollowed', () => {
  test('clear button removes all followed items', () => {
    const items = [
      { key: 'issues:a/b:1', dataType: 'issues', repo: 'a/b', number: 1, title: 'X', state: 'open' },
    ];
    localStorage.setItem('dashboardFollowed', JSON.stringify(items));
    document.body.innerHTML = `
      <div id="followed-container"></div>
      <button id="clear-followed">Clear</button>`;
    loadModule();

    // Verify item rendered
    expect(document.getElementById('followed-container').innerHTML).toContain('X');

    // Click clear
    document.getElementById('clear-followed').click();

    // Storage should be cleared and empty state shown
    expect(localStorage.getItem('dashboardFollowed')).toBeNull();
    expect(document.getElementById('followed-container').innerHTML).toContain('No followed items yet');
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------
describe('error handling', () => {
  test('corrupt localStorage shows error alert', () => {
    localStorage.setItem('dashboardFollowed', '{{corrupt}}');
    document.body.innerHTML = '<div id="followed-container"></div>';
    loadModule();

    expect(document.getElementById('followed-container').innerHTML).toContain('alert-danger');
  });

  test('no container element exits silently', () => {
    document.body.innerHTML = '<div id="other"></div>';
    expect(() => loadModule()).not.toThrow();
  });
});
