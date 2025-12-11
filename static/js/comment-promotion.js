(function () {
  const modal = document.querySelector('[data-comment-promote-modal]');
  if (!modal) {
    return;
  }

  const form = modal.querySelector('[data-comment-promote-form]');
  const descriptionField = form.querySelector('[data-comment-promote-description]');
  const contactField = form.querySelector('[data-comment-promote-contact]');
  const statusField = form.querySelector('[data-comment-promote-status]');
  const contextField = form.querySelector('[data-comment-promote-context]');
  const errorBox = form.querySelector('[data-comment-promote-error]');
  const cancelButton = form.querySelector('[data-comment-promote-cancel]');
  const submitButton = form.querySelector('[data-comment-promote-submit]');
  const warningBox = form.querySelector('[data-comment-promote-warning]');
  const warningText = form.querySelector('[data-comment-promote-warning-text]');
  const overrideRow = form.querySelector('[data-comment-promote-override-row]');
  const overrideField = form.querySelector('[data-comment-promote-override]');

  const supportsDialog = typeof modal.showModal === 'function';
  let activeCommentId = null;
  let activeExistingRequestId = null;

  function openModal() {
    if (supportsDialog) {
      modal.showModal();
    } else {
      modal.setAttribute('open', 'true');
    }
  }

  function closeModal() {
    if (supportsDialog) {
      modal.close();
    } else {
      modal.removeAttribute('open');
    }
    activeCommentId = null;
    activeExistingRequestId = null;
    errorBox.hidden = true;
    errorBox.textContent = '';
    warningBox.hidden = true;
    warningText.textContent = '';
    overrideRow.hidden = true;
    overrideField.checked = false;
  }

  function setError(message) {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  }

  function showExistingWarning(requestId) {
    activeExistingRequestId = requestId;
    warningText.innerHTML = `This comment already created <a href="/requests/${requestId}" target="_blank" rel="noopener">request #${requestId}</a>. Check the box below if you intentionally want to create another request.`;
    warningBox.hidden = false;
    overrideRow.hidden = false;
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-comment-promote]');
    if (!trigger) {
      return;
    }

    const commentId = trigger.getAttribute('data-comment-promote-id');
    if (!commentId) {
      return;
    }

    const container = trigger.closest('[data-comment-id]');
    const username = container?.getAttribute('data-comment-username') || 'member';
    const displayName = container?.getAttribute('data-comment-display-name') || '';
    const body = container?.querySelector('[data-comment-body-text]')?.textContent?.trim() || '';
    const promotedRequestId = container?.getAttribute('data-comment-promoted-request');

    activeCommentId = commentId;
    descriptionField.value = body;
    contactField.value = '';
    statusField.value = 'open';
    const label = displayName ? `${displayName} (@${username})` : `@${username}`;
    contextField.textContent = `Promoting comment from ${label}`;
    setError('');
    warningBox.hidden = true;
    warningText.textContent = '';
    overrideRow.hidden = true;
    overrideField.checked = false;
    if (promotedRequestId) {
      showExistingWarning(promotedRequestId);
    }
    openModal();
  });

  cancelButton?.addEventListener('click', (event) => {
    event.preventDefault();
    closeModal();
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!activeCommentId) {
      return;
    }

    setError('');
    submitButton.disabled = true;

    try {
      const payload = {
        description: descriptionField.value.trim(),
        contact_email: contactField.value.trim() || null,
        status: statusField.value || null,
        force: !!overrideField?.checked,
      };

      const response = await fetch(`/api/comments/${activeCommentId}/promote`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 409 && data?.detail) {
          const detail = data.detail;
          const targetId = typeof detail === 'object' ? detail.promoted_request_id : null;
          if (targetId) {
            showExistingWarning(targetId);
          }
          const message =
            (typeof detail === 'object' && detail.message) ||
            (typeof detail === 'string' ? detail : 'Comment already promoted. Enable the override to continue.');
          throw new Error(message);
        }
        const detail = data?.detail || data?.error || 'Failed to promote comment';
        throw new Error(detail);
      }

      if (data && data.id) {
        window.location.href = `/requests/${data.id}`;
      } else {
        closeModal();
      }
    } catch (error) {
      setError(error.message || 'Unable to promote comment');
    } finally {
      submitButton.disabled = false;
    }
  });

  if (!supportsDialog) {
    modal.setAttribute('role', 'dialog');
  }
})();
