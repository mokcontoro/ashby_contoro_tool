# Ashby Resume Downloader

A Flask web application for downloading candidate resumes from Ashby ATS in bulk.

## Features

- **Resume Downloader**: Fetch and download resumes for candidates in the "Application Review" stage
  - Select a job posting to view candidates
  - Automatically filters to "Application Review" stage
  - Download individual resumes or bulk download as ZIP
  - Sort candidates by name or application date
  - Batch selection for large candidate lists

- **PDF Combiner**: Combine multiple PDF files into grouped documents
  - Upload a ZIP file containing PDFs
  - Specify how many PDFs to combine per output file
  - Download combined PDFs as a ZIP

## Requirements

- Python 3.8+
- Ashby API key
- Dependencies listed in `requirements.txt`

## Setup

1. Clone the repository

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your configuration:
   ```
   ASHBY_API_KEY=your_ashby_api_key
   APP_PASSKEY=your_login_passkey
   SECRET_KEY=your_flask_secret_key
   ```

4. Run the application:
   ```bash
   python app.py
   ```

5. Access at `http://localhost:5000`

## Deployment

The application includes a `Procfile` for deployment to platforms like Railway or Heroku:

```bash
gunicorn app:app --timeout 300
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ASHBY_API_KEY` | Your Ashby API key | Yes |
| `APP_PASSKEY` | Password for login authentication | Yes |
| `SECRET_KEY` | Flask session secret key | No (auto-generated if not set) |

## Version

Current version: 1.1.0

## Changelog

### v1.1.0
- Removed interview stage selection
- Auto-filter to "Application Review" stage only
- Simplified UI workflow

### v1.0.0
- Initial release
- Resume downloader with stage selection
- PDF combiner tool
- Bulk download functionality
- Batch selection for candidates
