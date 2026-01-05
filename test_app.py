import pytest
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
