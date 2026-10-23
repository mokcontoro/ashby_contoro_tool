(() => {
    const host = document.getElementById('ashby-feedback');
    const privacy = 'Reports and screenshots go to the Ashby Tools GitHub issue tracker and follow repository access permissions. Review the images and metadata below before sending; remove anything private.';
    async function initialize() {
        try {
            const response = await fetch('/api/feedback');
            if (!response.ok) throw new Error('Please refresh the page and sign in again.');
            const config = await response.json();
            host.replaceChildren();
            const widget = NoliziFeedback.mount({
                container: host, endpoint: '/api/feedback', product: 'Ashby Tools',
                version: config.version, capture: true, captureRoot: 'body',
                copy: { title: 'Share feedback', send: 'Submit feedback', privacy,
                    intro: 'Report a problem, suggest an idea, or ask a question. Screenshots and diagnostics can help us understand what happened.',
                    autoNote: 'Captured automatically. Click to inspect it, or remove it before sending.' },
                send: async payload => {
                    // Refresh the CSRF token if this page has been open a while.
                    const current = await fetch('/api/feedback');
                    if (!current.ok) throw new Error('Please sign in again. Your draft is still here.');
                    const settings = await current.json();
                    const result = await fetch('/api/feedback', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': settings.csrfToken},
                        body: JSON.stringify({...payload, sharingConsent: true}),
                    });
                    let data;
                    try { data = await result.json(); }
                    catch { throw new Error('Could not confirm submission. Check GitHub issues before retrying.'); }
                    if (!result.ok) throw new Error(data.error || 'Could not send feedback.');
                    return data;
                },
            });
            const note = document.createElement('p');
            note.className = 'nl-feedback__privacy'; note.textContent = privacy;
            widget.dialog.querySelector('form').prepend(note);
        } catch (error) {
            host.replaceChildren();
            const retry = document.createElement('button');
            retry.className = 'nl-button nl-feedback-trigger';
            retry.textContent = 'Feedback unavailable ? retry';
            retry.title = error.message;
            retry.addEventListener('click', initialize);
            host.append(retry);
        }
    }
    initialize();
})();
