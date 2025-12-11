(function () {
  const container = document.querySelector('[data-chat-search]');
  if (!container) {
    return;
  }

  const form = container.querySelector('[data-chat-search-form]');
  const input = container.querySelector('[data-chat-search-input]');
  const resultsList = container.querySelector('[data-chat-search-results]');
  const statusEl = container.querySelector('[data-chat-search-status]');
  const template = document.querySelector('#chat-search-result-template');
  const requestId = container.getAttribute('data-request-id');
  const panel = container.querySelector('[data-chat-search-panel]');
  const toggle = container.querySelector('[data-chat-search-toggle]');
  if (!form || !input || !resultsList || !template || !requestId) {
    return;
  }

  if (panel && toggle) {
    const setCollapsed = (collapsed) => {
      panel.hidden = collapsed;
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      toggle.textContent = collapsed ? 'Show' : 'Hide';
      container.classList.toggle('request-chat-search--collapsed', collapsed);
    };

    setCollapsed(true);
    toggle.addEventListener('click', () => {
      setCollapsed(!panel.hidden);
    });
  }

  let debounceTimer;
  let currentAbort;

  const escapeHTML = (value) => {
    return String(value || '').replace(/[&<>]/g, (char) => {
      switch (char) {
        case '&':
          return '&amp;';
        case '<':
          return '&lt;';
        case '>':
          return '&gt;';
        default:
          return char;
      }
    });
  };

  const highlightBody = (body, tokens) => {
    let html = escapeHTML(body);
    (tokens || []).forEach((token) => {
      if (!token) {
        return;
      }
      const escapedToken = token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const pattern = new RegExp(`(${escapedToken})`, 'gi');
      html = html.replace(pattern, '<mark>$1</mark>');
    });
    return html;
  };

  const setStatus = (message) => {
    if (statusEl) {
      statusEl.textContent = message || '';
    }
  };

  const clearResults = () => {
    resultsList.innerHTML = '';
  };

  const runSearch = () => {
    const query = input.value.trim();
    if (currentAbort) {
      currentAbort.abort();
    }
    const controller = new AbortController();
    currentAbort = controller;

    if (!query) {
      clearResults();
      setStatus('');
      return;
    }

    const url = new URL(`/requests/${requestId}/chat-search`, window.location.origin);
    url.searchParams.set('q', query);

    if (!window.fetch) {
      form.submit();
      return;
    }

    setStatus('Searching…');
    fetch(url.toString(), {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Search failed (${response.status})`);
        }
        return response.json();
      })
      .then((payload) => {
        clearResults();
        const results = payload.results || [];
        results.forEach((entry) => {
          const fragment = template.content.cloneNode(true);
          const profileLink = fragment.querySelector('[data-author-link]');
          const timeLink = fragment.querySelector('[data-time-link]');
          const time = fragment.querySelector('[data-time]');
          const body = fragment.querySelector('[data-body]');
          const tags = fragment.querySelector('[data-tags]');

          if (profileLink) {
            profileLink.href = `/people/${entry.username}`;
            profileLink.textContent = entry.display_name || `@${entry.username}`;
            profileLink.title = entry.display_name ? `@${entry.username}` : '';
          }
          if (timeLink && time) {
            time.textContent = new Date(entry.created_at).toLocaleString();
            time.dateTime = entry.created_at || '';
            timeLink.href = `#${entry.comment_anchor || entry.anchor}`;
          }
          if (body) {
            body.innerHTML = highlightBody(entry.body, entry.matched_tokens);
          }
          if (tags) {
            tags.innerHTML = '';
            (entry.topics || []).forEach((topic) => {
              const span = document.createElement('span');
              span.className = 'meta-chip meta-chip--small';
              span.textContent = topic;
              tags.appendChild(span);
            });
            (entry.ai_topics || []).forEach((topic) => {
              const span = document.createElement('span');
              span.className = 'meta-chip meta-chip--small meta-chip--ghost';
              span.textContent = topic;
              tags.appendChild(span);
            });
            if (!tags.children.length) {
              tags.remove();
            }
          }

          resultsList.appendChild(fragment);
        });
        setStatus(
          results.length ? `${results.length} result${results.length === 1 ? '' : 's'}` : 'No matches'
        );
      })
      .catch((error) => {
        if (error.name === 'AbortError') {
          return;
        }
        console.error('Chat search failed', error);
        setStatus('Search failed. Try again.');
      });
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch();
  });

  input.addEventListener('input', () => {
    if (debounceTimer) {
      window.clearTimeout(debounceTimer);
    }
    debounceTimer = window.setTimeout(runSearch, 350);
  });
})();
