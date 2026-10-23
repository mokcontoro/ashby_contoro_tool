(() => {
    const byId = id => document.getElementById(id);
    const dialog = byId('feedback-dialog');
    const form = byId('feedback-form');
    const submit = byId('feedback-submit');
    const status = byId('feedback-status');
    const result = byId('feedback-result');
    const areas = {downloader: 'Resume Downloader', combiner: 'PDF Combiner'};
    let config;
    let area = 'downloader';
    let sending = false;
    let draftPrepared = false;

    function say(message, error = false) {
        status.textContent = message;
        status.dataset.error = String(error);
    }
    function updatePreview() {
        const context = `Version: ${config ? config.version : 'Loading...'}\nTool: ${areas[area]}`;
        byId('feedback-context').textContent = context.replace('\n', ' · ');
        byId('feedback-preview').textContent = [
            `Type: ${byId('feedback-type').selectedOptions[0].textContent}`,
            `Title: ${byId('feedback-title').value.trim() || '(not entered)'}`,
            byId('feedback-message').value.trim() || '(no details yet)',
            byId('feedback-diagnostics').checked ? context : 'App context excluded.',
        ].join('\n\n');
    }
    function showLink(url, text) {
        result.href = url;
        result.textContent = text;
        result.hidden = false;
    }
    async function open() {
        if (!dialog.open) dialog.showModal();
        // Preserve the original context with an existing draft.
        if (!byId('feedback-title').value && !byId('feedback-message').value) {
            area = document.querySelector('.tab.active')?.dataset.tab === 'combiner' ? 'combiner' : 'downloader';
        }
        submit.disabled = true;
        say('Loading feedback...');
        try {
            const response = await fetch('/api/feedback');
            if (!response.ok) throw new Error('Could not open feedback. Refresh the page and sign in again if needed.');
            config = await response.json();
            submit.textContent = config.direct ? 'Submit public feedback' : 'Continue on GitHub';
            byId('feedback-mode').textContent = config.direct
                ? 'Submitting creates a public GitHub issue. You can add screenshots to that issue afterward.'
                : 'The next step opens a prefilled issue on GitHub. Sign in, add any screenshots, and click Create to submit it.';
            submit.disabled = false;
            say('');
        } catch (error) {
            say(error.message, true);
            submit.textContent = 'Reopen to retry';
        }
        updatePreview();
    }
    byId('feedback-open').addEventListener('click', open);
    byId('feedback-close').addEventListener('click', () => { if (!sending) dialog.close(); });
    dialog.addEventListener('cancel', event => { if (sending) event.preventDefault(); });
    form.addEventListener('input', () => {
        updatePreview();
        if (draftPrepared) { result.hidden = true; draftPrepared = false; say(''); }
    });
    byId('feedback-discard').addEventListener('click', () => {
        form.reset(); result.hidden = true; draftPrepared = false; say(''); updatePreview();
    });
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (sending || !config || !form.reportValidity()) return;
        sending = true;
        const payload = {
            type: byId('feedback-type').value,
            title: byId('feedback-title').value.trim(),
            message: byId('feedback-message').value.trim(),
            area,
            includeDiagnostics: byId('feedback-diagnostics').checked,
            publicConsent: byId('feedback-consent').checked,
        };
        const controls = [...form.querySelectorAll('input, select, textarea, button')];
        controls.forEach(control => { control.disabled = true; });
        byId('feedback-close').disabled = true;
        result.hidden = true;
        say(config.direct ? 'Submitting feedback...' : 'Preparing your GitHub draft...');
        try {
            const response = await fetch('/api/feedback', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-CSRF-Token': config.csrfToken},
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) {
                if (data.issuesUrl) showLink(data.issuesUrl, 'Check existing GitHub issues');
                throw new Error(data.error || 'Could not submit feedback. Your draft is still here.');
            }
            if (data.submitted) {
                say('Your feedback was submitted. Thank you.');
                showLink(data.issueUrl, 'View your issue or add screenshots on GitHub');
                form.reset();
                updatePreview();
            } else {
                say('Your draft is ready. It has not been submitted yet. Open GitHub to finish.');
                showLink(data.draftUrl, 'Open prefilled issue on GitHub');
                draftPrepared = true;
                result.focus();
            }
        } catch (error) {
            say(error instanceof SyntaxError ? 'Could not confirm submission. Check GitHub before retrying; your draft is still here.' : error.message, true);
        } finally {
            controls.forEach(control => { control.disabled = false; });
            byId('feedback-close').disabled = false;
            sending = false;
        }
    });
})();
