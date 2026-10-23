"""Bounded diagnostics and screenshot uploads for the shared feedback widget."""
import base64
import hashlib
import json
import math
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests

REPO = 'mokcontoro/ashby_contoro_tool'
API = f'https://api.github.com/repos/{REPO}'
BRANCH = 'feedback-attachments'


def clean_url(value):
    try:
        url = urlsplit(str(value))
        if url.scheme not in ('http', 'https') or not url.hostname:
            return 'REDACTED'
        path = re.sub(r'(/api/jobs/)[^/]+', r'\1REDACTED', url.path)
        path = re.sub(r'(/api/download-resume/)[^/]+', r'\1REDACTED', path)
        query = urlencode([(key, 'REDACTED') for key, _ in parse_qsl(url.query)])
        return urlunsplit((url.scheme, url.hostname, path, query, ''))[:512]
    except ValueError:
        return 'REDACTED'


def clean_text(value):
    text = str(value)[:1000]
    text = re.sub(r'https?://[^\s<>"\x27`]+', lambda m: clean_url(m[0]), text)
    text = re.sub(r'(?i)(bearer\s+)[\w.~-]+', r'\1REDACTED', text)
    text = re.sub(r'(?i)((?:password|token|secret|authorization|cookie|code|state)\s*[:=]\s*)[^\s,;&]+', r'\1REDACTED', text)
    return re.sub(r'[`<>]', '', text)[:180]


def row(value, keys):
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in keys:
        if key not in value:
            continue
        item = value[key]
        if key == 'url':
            result[key] = clean_url(item)
        elif isinstance(item, bool):
            result[key] = item
        elif isinstance(item, (int, float)) and math.isfinite(item):
            result[key] = max(-1, min(item, 1e13))
        elif isinstance(item, str):
            result[key] = clean_text(item)
    return result


def diagnostics(data, version):
    result = row(data, ['viewport', 'timezone', 'userAgent', 'online'])
    result.update(product='Ashby Tools', version=version, page=clean_url(data.get('page', '')))
    errors = data.get('errors', [])
    result['errors'] = [row(e, ['message', 'source', 'at', 'lineno', 'colno'])
                        for e in errors[-10:]] if isinstance(errors, list) else []
    repro = data.get('reproduction')
    if isinstance(repro, dict) and repro.get('version') == 1:
        record = row(repro, ['id', 'opened_at', 'url', 'viewport', 'scroll_x', 'scroll_y',
                            'visibility', 'language', 'online', 'connection'])
        record['version'] = 1
        for name, limit, keys in [
            ('actions', 30, ['at', 'kind', 'control', 'url', 'disabled', 'invalid']),
            ('requests', 20, ['at', 'kind', 'url', 'method', 'status', 'duration_ms', 'outcome', 'request_id', 'redirected']),
            ('controls', 30, ['control', 'type', 'disabled', 'invalid', 'checked', 'expanded'])]:
            items = repro.get(name, [])
            record[name] = [row(x, keys) for x in items[-limit:]] if isinstance(items, list) else []
        result['reproduction'] = record
    return result


def validate_images(images):
    if not isinstance(images, list) or len(images) > 5:
        raise ValueError('Attach up to 5 images.')
    total = 0
    validated = []
    for image in images:
        if not isinstance(image, dict) or not isinstance(image.get('data'), str):
            raise ValueError('Choose PNG, JPEG, or WebP images.')
        match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})', image['data'])
        if not match or len(match[2]) > 5600000:
            raise ValueError('Each image must be PNG, JPEG, or WebP and at most 4 MB.')
        try:
            raw = base64.b64decode(match[2], validate=True)
        except ValueError:
            raise ValueError('Invalid image data.') from None
        kind = match[1]
        valid = ((kind == 'png' and raw.startswith(b'\x89PNG\r\n\x1a\n'))
                 or (kind == 'jpeg' and raw.startswith(b'\xff\xd8\xff'))
                 or (kind == 'webp' and raw.startswith(b'RIFF') and raw[8:12] == b'WEBP'))
        if not valid or len(raw) > 4 * 1024 * 1024:
            raise ValueError('Each image must be a valid PNG, JPEG, or WebP and at most 4 MB.')
        total += len(raw)
        if total > 12 * 1024 * 1024:
            raise ValueError('Images must total 12 MB or less.')
        extension = 'jpg' if kind == 'jpeg' else kind
        path = f'.github/feedback-attachments/{hashlib.sha256(raw).hexdigest()}.{extension}'
        validated.append((path, match[2]))
    return validated


def github(method, path, token, **kwargs):
    return requests.request(method, API + path,
                            headers={'Authorization': f'Bearer {token}',
                                     'Accept': 'application/vnd.github+json',
                                     'X-GitHub-Api-Version': '2022-11-28'},
                            timeout=30, **kwargs)


def upload_images(images, token):
    if not images:
        return []
    branch = github('GET', f'/git/ref/heads/{BRANCH}', token)
    if branch.status_code == 404:
        main = github('GET', '/git/ref/heads/main', token)
        main.raise_for_status()
        created = github('POST', '/git/refs', token, json={
            'ref': f'refs/heads/{BRANCH}', 'sha': main.json()['object']['sha']})
        if created.status_code != 201:
            # Another request may have initialized the branch concurrently.
            github('GET', f'/git/ref/heads/{BRANCH}', token).raise_for_status()
    else:
        branch.raise_for_status()
    urls = []
    for path, content in images:
        existing = github('GET', f'/contents/{path}', token, params={'ref': BRANCH})
        if existing.status_code == 404:
            saved = github('PUT', f'/contents/{path}', token, json={
                'message': 'Attach feedback screenshot', 'content': content, 'branch': BRANCH})
            if saved.status_code != 201:
                # The content-addressed path makes retries safe and deduplicates images.
                github('GET', f'/contents/{path}', token, params={'ref': BRANCH}).raise_for_status()
        else:
            existing.raise_for_status()
        urls.append(f'https://github.com/{REPO}/blob/{BRANCH}/{path}?raw=true')
    return urls


def prepare_report(data, version):
    kinds = {'bug': 'Bug', 'feature': 'Feature request', 'question': 'Question', 'general': 'General feedback'}
    kind = data.get('type')
    message = data.get('message')
    email = data.get('email', '')
    if not isinstance(kind, str) or kind not in kinds:
        raise ValueError('Choose a feedback type.')
    if not isinstance(message, str) or not 3 <= len(message.strip()) <= 5000:
        raise ValueError('Enter a message of 3–5,000 characters.')
    if not isinstance(email, str) or len(email) > 254 or '\n' in email or '\r' in email:
        raise ValueError('Enter a valid contact email or leave it blank.')
    images = validate_images(data.get('images', []))
    title = f'[Feedback] {kinds[kind]}: ' + ' '.join(message.split())[:100]
    body = f'### {kinds[kind]}\n\n{message.strip()}\n'
    if email.strip():
        body += '\n### Contact email\n' + email.strip() + '\n'
    body += '\n### Included diagnostics\n\n```json\n' + json.dumps(diagnostics(data, version), indent=2) + '\n```\n'
    return title, body, images
