from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock, patch

import pytest
import requests

from app import app
from feedback import ISSUES_URL


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('GITHUB_FEEDBACK_TOKEN', raising=False)
    app.config.update(TESTING=True, SECRET_KEY='test-feedback-key')
    with app.test_client() as client:
        with client.session_transaction() as session:
            session['authenticated'] = True
        yield client


def submit(client, **changes):
    config = client.get('/api/feedback').get_json()
    payload = dict(type='bug', title='Example issue', message='Synthetic test feedback',
                   area='downloader', includeDiagnostics=True, publicConsent=True)
    payload.update(changes)
    return client.post('/api/feedback', json=payload, headers={'X-CSRF-Token': config['csrfToken']})


def test_requires_login():
    with app.test_client() as client:
        assert client.get('/api/feedback').status_code == 401
        assert client.post('/api/feedback').status_code == 401


def test_csrf_is_required(client):
    assert client.post('/api/feedback', json={}).status_code == 403
    config = client.get('/api/feedback')
    assert config.headers['Cache-Control'] == 'no-store'
    assert client.post('/api/feedback', json={}, headers={'X-CSRF-Token': 'wrong'}).status_code == 403


@pytest.mark.parametrize('changes', [dict(type=[]), dict(type='invalid'), dict(title=' '),
    dict(title='x' * 101), dict(message=''), dict(message='x' * 2001),
    dict(message={}), dict(area='/candidate/private'), dict(publicConsent=False)])
def test_validation(client, changes):
    assert submit(client, **changes).status_code == 400


def test_no_token_returns_explicit_draft_and_drops_private_fields(client):
    with patch('feedback.requests.post') as post:
        response = submit(client, email='private@example.test', candidate='PRIVATE-CANDIDATE',
                          url='https://example.test/?secret=PRIVATE-TOKEN', errors=['PRIVATE-ERROR'])
    post.assert_not_called()
    assert response.status_code == 200
    data = response.get_json()
    assert data['submitted'] is False
    parsed = urlparse(data['draftUrl'])
    assert parsed.netloc == 'github.com'
    assert parsed.path == '/mokcontoro/ashby_contoro_tool/issues/new'
    body = parse_qs(parsed.query)['body'][0]
    assert 'Synthetic test feedback' in body
    assert 'Version:' in body
    assert 'PRIVATE' not in body and 'private@example' not in body


def test_diagnostics_can_be_excluded(client):
    data = submit(client, includeDiagnostics=False).get_json()
    body = parse_qs(urlparse(data['draftUrl']).query)['body'][0]
    assert 'Version:' not in body and 'App context' not in body


def test_direct_submission(client, monkeypatch):
    monkeypatch.setenv('GITHUB_FEEDBACK_TOKEN', 'test-only-token')
    assert client.get('/api/feedback').get_json()['direct'] is True
    with patch('feedback.requests.post', return_value=Mock(status_code=201,
               json=lambda: {'html_url': ISSUES_URL + '/42'})) as post:
        response = submit(client)
    assert response.status_code == 201
    assert response.get_json() == {'submitted': True, 'issueUrl': ISSUES_URL + '/42'}
    assert post.call_args.args[0] == 'https://api.github.com/repos/mokcontoro/ashby_contoro_tool/issues'
    assert post.call_args.kwargs['timeout'] == 20
    assert 'test-only-token' not in response.get_data(as_text=True)


def test_github_error_never_reports_success(client, monkeypatch):
    monkeypatch.setenv('GITHUB_FEEDBACK_TOKEN', 'test-only-token')
    with patch('feedback.requests.post', return_value=Mock(status_code=403)):
        response = submit(client)
    assert response.status_code == 502
    assert 'submitted' not in response.get_json()


def test_timeout_does_not_retry_or_lose_uncertainty(client, monkeypatch):
    monkeypatch.setenv('GITHUB_FEEDBACK_TOKEN', 'test-only-token')
    with patch('feedback.requests.post', side_effect=requests.Timeout) as post:
        response = submit(client)
    assert response.status_code == 502
    post.assert_called_once()
    assert response.get_json()['issuesUrl'] == ISSUES_URL


def test_external_issue_url_is_rejected(client, monkeypatch):
    monkeypatch.setenv('GITHUB_FEEDBACK_TOKEN', 'test-only-token')
    with patch('feedback.requests.post', return_value=Mock(status_code=201,
               json=lambda: {'html_url': 'https://example.test/elsewhere'})):
        assert submit(client).status_code == 502
