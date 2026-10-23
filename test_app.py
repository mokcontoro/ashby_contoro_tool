import pytest
import io
import zipfile
from pypdf import PdfReader, PdfWriter
from unittest.mock import patch, MagicMock
from app import app, __version__


@pytest.fixture
def client():
    """Create a test client."""
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key'
    with app.test_client() as client:
        yield client


@pytest.fixture
def authenticated_client(client):
    """Create an authenticated test client."""
    with client.session_transaction() as sess:
        sess['authenticated'] = True
    return client


class TestVersion:
    """Test version information."""

    def test_version_exists(self):
        """Test that version is defined."""
        assert __version__ is not None

    def test_version_format(self):
        """Test that version follows semantic versioning."""
        parts = __version__.split('.')
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)


class TestAuthentication:
    """Test authentication routes."""

    def test_login_page_loads(self, client):
        """Test that login page loads."""
        response = client.get('/login')
        assert response.status_code == 200

    def test_unauthenticated_redirect(self, client):
        """Test that unauthenticated users are redirected."""
        response = client.get('/')
        assert response.status_code == 302
        assert '/login' in response.location

    def test_authenticated_access(self, authenticated_client):
        """Test that authenticated users can access main page."""
        response = authenticated_client.get('/')
        assert response.status_code == 200

    def test_logout(self, authenticated_client):
        """Test logout clears session."""
        response = authenticated_client.get('/logout')
        assert response.status_code == 302


class TestAPIEndpoints:
    """Test API endpoints."""

    def test_jobs_requires_auth(self, client):
        """Test that /api/jobs requires authentication."""
        response = client.get('/api/jobs')
        assert response.status_code == 401

    def test_candidates_requires_auth(self, client):
        """Test that /api/candidates requires authentication."""
        response = client.get('/api/candidates')
        assert response.status_code == 401

    def test_candidates_requires_job_id(self, authenticated_client):
        """Test that /api/candidates requires job ID."""
        response = authenticated_client.get('/api/candidates')
        assert response.status_code == 400

    @patch('app.ashby_request_paginated')
    def test_jobs_endpoint(self, mock_ashby, authenticated_client):
        """Test /api/jobs endpoint with mocked Ashby API."""
        mock_ashby.return_value = {
            'success': True,
            'results': [
                {
                    'id': 'job-1',
                    'title': 'Software Engineer',
                    'status': 'Open',
                    'department': {'name': 'Engineering'},
                    'location': {'name': 'Remote'}
                }
            ]
        }
        response = authenticated_client.get('/api/jobs')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert data[0]['title'] == 'Software Engineer'

    @patch('app.ashby_request')
    def test_stages_endpoint(self, mock_ashby, authenticated_client):
        """Test /api/jobs/<job_id>/stages endpoint."""
        mock_ashby.side_effect = [
            {'success': True, 'results': {'defaultInterviewPlanId': 'plan-1'}},
            {'success': True, 'results': [
                {'id': 'stage-1', 'title': 'Application Review', 'type': 'ApplicationReview', 'orderInInterviewPlan': 1}
            ]}
        ]
        response = authenticated_client.get('/api/jobs/job-1/stages')
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert data[0]['title'] == 'Application Review'


class TestPDFCombiner:
    """Test PDF combiner functionality."""

    def test_combine_requires_auth(self, client):
        """Test that PDF combiner requires authentication."""
        response = client.post('/api/combine-pdfs')
        assert response.status_code == 401

    def test_combine_requires_file(self, authenticated_client):
        """Test that PDF combiner requires a file."""
        response = authenticated_client.post('/api/combine-pdfs')
        assert response.status_code == 400


class TestMergedDownload:
    def test_requires_auth(self, client):
        assert client.post('/api/download-merged').status_code == 401

    @pytest.mark.parametrize('payload', [None, [], {}, {'fileHandles': 'a'},
        {'fileHandles': [None]}, {'fileHandles': ['a'], 'pdfsPerFile': 0},
        {'fileHandles': ['a'], 'pdfsPerFile': 1.5},
        {'fileHandles': ['a'], 'pdfsPerFile': True}])
    def test_invalid_input(self, authenticated_client, payload):
        assert authenticated_client.post('/api/download-merged', json=payload).status_code == 400

    @patch('app.requests.get')
    @patch('app.ashby_request')
    def test_groups_preserve_resume_and_page_order(self, ashby, get, authenticated_client):
        pdfs = {}
        for handle, widths in [('a', [100, 101]), ('b', [200]), ('c', [300])]:
            writer = PdfWriter()
            for width in widths:
                writer.add_blank_page(width=width, height=400)
            buffer = io.BytesIO()
            writer.write(buffer)
            pdfs[handle] = buffer.getvalue()
        ashby.side_effect = lambda endpoint, data: {'success': True, 'results': {'url': data['fileHandle']}}
        get.side_effect = lambda url, **kwargs: MagicMock(content=pdfs[url])
        response = authenticated_client.post('/api/download-merged', json={
            'fileHandles': ['c', 'a', 'b'], 'pdfsPerFile': 2})
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            assert archive.namelist() == ['combined_001.pdf', 'combined_002.pdf']
            widths = [[int(page.mediabox.width) for page in
                       PdfReader(io.BytesIO(archive.read(name))).pages]
                      for name in archive.namelist()]
            assert widths == [[300, 100, 101], [200]]
        assert all(call.kwargs['timeout'] == 30 for call in get.call_args_list)

    @patch('app.ashby_request', return_value={'success': False})
    def test_download_failure_returns_error(self, ashby, authenticated_client):
        response = authenticated_client.post('/api/download-merged', json={'fileHandles': ['a']})
        assert response.status_code == 502
        assert response.is_json

    @patch('app.requests.get')
    @patch('app.ashby_request')
    def test_invalid_pdf_is_not_silently_skipped(self, ashby, get, authenticated_client):
        ashby.return_value = {'success': True, 'results': {'url': 'resume'}}
        get.return_value = MagicMock(content=b'not a PDF')
        response = authenticated_client.post('/api/download-merged', json={'fileHandles': ['a']})
        assert response.status_code == 422
        assert 'resume 1' in response.get_json()['error']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
