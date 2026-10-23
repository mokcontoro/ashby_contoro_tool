"""Authenticated feedback, limited to this application's GitHub repository."""
import os
import re
import secrets
import json
from urllib.parse import urlencode

import requests
from flask import jsonify, request, session
from feedback_details import prepare_report, upload_images

REPO = 'mokcontoro/ashby_contoro_tool'
ISSUES_URL = f'https://github.com/{REPO}/issues'
KINDS = {'bug': 'Bug', 'feature': 'Feature request', 'general': 'General feedback'}
AREAS = {'downloader': 'Resume Downloader', 'combiner': 'PDF Combiner'}


def register_feedback(app, login_required, version):
    @app.get('/api/feedback')
    @login_required
    def feedback_config():
        session.setdefault('feedback_csrf', secrets.token_urlsafe(32))
        response = jsonify({
            'csrfToken': session['feedback_csrf'],
            'direct': bool(os.getenv('GITHUB_FEEDBACK_TOKEN')),
            'version': version,
            'repository': REPO,
        })
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/feedback')
    @login_required
    def feedback_submit():
        expected = session.get('feedback_csrf', '')
        provided = request.headers.get('X-CSRF-Token', '')
        if not expected or not secrets.compare_digest(expected, provided):
            return jsonify({'error': 'Please reopen Feedback and try again.'}), 403
        max_bytes = 20 * 1024 * 1024
        if request.content_length and request.content_length > max_bytes:
            return jsonify({'error': 'Feedback is too long.'}), 413
        raw = request.stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return jsonify({'error': 'Feedback is too long.'}), 413
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            return jsonify({'error': 'A feedback form is required.'}), 400
        if 'images' in data:
            return submit_detailed(data)
        kind = data.get('type')
        title = data.get('title')
        message = data.get('message')
        if not isinstance(kind, str) or kind not in KINDS:
            return jsonify({'error': 'Choose a feedback type.'}), 400
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
            return jsonify({'error': 'Enter a title of 1–100 characters.'}), 400
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
            return jsonify({'error': 'Enter a description of 1–2,000 characters.'}), 400
        # Accept the previous field name for pages opened before deployment.
        if data.get('sharingConsent', data.get('publicConsent')) is not True:
            return jsonify({'error': 'Confirm that you agree to send this feedback to the issue tracker.'}), 400

        # Only fixed, visible diagnostic fields are allowed. Never forward the
        # submitted object, URLs, names, resume handles, or arbitrary logs.
        area = data.get('area')
        if not isinstance(area, str) or area not in AREAS:
            return jsonify({'error': 'Choose a valid application area.'}), 400
        issue_title = f'[Feedback] {KINDS[kind]}: ' + ' '.join(title.split())
        body = f'### {KINDS[kind]}\n\n{message.strip()}'
        if data.get('includeDiagnostics') is True:
            body += f'\n\n### App context\n- Version: {version}\n- Area: {AREAS[area]}'
        token = os.getenv('GITHUB_FEEDBACK_TOKEN')
        if not token:
            return jsonify({'draftUrl': ISSUES_URL + '/new?' + urlencode({
                'title': issue_title, 'body': body,
            }), 'submitted': False})
        try:
            response = requests.post(
                f'https://api.github.com/repos/{REPO}/issues',
                headers={'Authorization': f'Bearer {token}',
                         'Accept': 'application/vnd.github+json',
                         'X-GitHub-Api-Version': '2022-11-28'},
                json={'title': issue_title, 'body': body}, timeout=20,
            )
            if response.status_code != 201:
                app.logger.warning('Feedback issue creation returned HTTP %s', response.status_code)
                return jsonify({'error': 'GitHub could not create the issue. Your draft is still here.'}), 502
            result = response.json()
            issue_url = result.get('html_url', '')
            if not isinstance(issue_url, str) or not re.fullmatch(re.escape(ISSUES_URL) + r'/[0-9]+', issue_url):
                raise ValueError('Unexpected issue URL')
            return jsonify({'submitted': True, 'issueUrl': issue_url}), 201
        except (requests.RequestException, ValueError):
            # A timeout can occur after GitHub creates the issue. Don't retry
            # automatically or claim the report definitely failed.
            return jsonify({'error': 'Could not confirm submission. Check GitHub issues before retrying to avoid a duplicate.',
                            'issuesUrl': ISSUES_URL}), 502

    def submit_detailed(data):
        if data.get('sharingConsent') is not True:
            return jsonify({'error': 'Confirm that you agree to send this feedback to the issue tracker.'}), 400
        try:
            title, body, images = prepare_report(data, version)
        except ValueError as error:
            return jsonify({'error': str(error)}), 400
        token = os.getenv('GITHUB_FEEDBACK_TOKEN')
        if not token:
            return jsonify({'error': 'Feedback submission is not configured. Your message and images are still here.'}), 503
        try:
            urls = upload_images(images, token)
        except (requests.RequestException, ValueError, KeyError):
            return jsonify({'error': 'Screenshot upload failed. Check that the feedback token has Contents: Read and write. Your report has not been submitted; your images and message are still here.'}), 502
        for index, url in enumerate(urls, 1):
            body += f'\n### Screenshot {index}\n\n![Feedback screenshot {index}]({url})\n'
        if urls:
            body += '\nScreen capture may show a different tab or window from the reported page.\n'
        try:
            response = requests.post(f'https://api.github.com/repos/{REPO}/issues',
                                    headers={'Authorization': f'Bearer {token}',
                                             'Accept': 'application/vnd.github+json',
                                             'X-GitHub-Api-Version': '2022-11-28'},
                                    json={'title': title, 'body': body}, timeout=20)
            if response.status_code != 201:
                return jsonify({'error': 'GitHub could not create the issue. Your message and images are still here.'}), 502
            result = response.json()
            issue_url = result.get('html_url', '')
            if not isinstance(issue_url, str) or not re.fullmatch(re.escape(ISSUES_URL) + r'/[0-9]+', issue_url):
                raise ValueError('Unexpected issue URL')
            return jsonify({'ok': True, 'issueUrl': issue_url, 'reference': result.get('number')}), 201
        except (requests.RequestException, ValueError):
            return jsonify({'error': 'Could not confirm submission. Check GitHub issues before retrying to avoid a duplicate.', 'issuesUrl': ISSUES_URL}), 502
