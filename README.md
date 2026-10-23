# Ashby Resume Downloader

A Flask web application for downloading candidate resumes from Ashby ATS in bulk.

## Features

- **Resume Downloader**: Fetch and download resumes for candidates in the "Application Review" stage
  - Filter jobs to show only open positions (enabled by default)
  - Select a job posting to view candidates
  - Automatically filters to "Application Review" stage
  - Download individual resumes or bulk download as ZIP
  - One-step **Merge & Download Selected**: download selected resumes and merge them into grouped PDFs, delivered as a ZIP without saving and uploading intermediate files
  - Sort candidates by name or application date
  - Batch selection for large candidate lists

- **PDF Combiner**: Combine multiple PDF files into grouped documents
  - Upload a ZIP file containing PDFs
  - Specify how many PDFs to combine per output file
  - Download combined PDFs as a ZIP

## One-step merged download

Select a job, fetch candidates, and select the resumes to include. Set **Resumes per Merged PDF** (default: 10), then click **Merge & Download Selected**. The downloaded `merged_resumes.zip` contains numbered PDFs in the current candidate list order. Each resume stays intact within its group, including all of its pages. If a resume cannot be downloaded or is not a readable, unencrypted PDF, the app reports an error instead of silently omitting it.

The original download and ZIP-upload combiner remain available.

## Requirements

- Python 3.8+
- Ashby API key
- Dependencies listed in `requirements.txt`

## Feedback

Signed-in users can open **Feedback** from either tool to report bugs, suggest ideas, or ask questions. The widget reuses the Nolizi feedback implementation with Ashby-specific configuration. Reports go only to `mokcontoro/ashby_contoro_tool` and follow that repository's access permissions.

Features include an automatic removable page screenshot, manual page capture, browser screen/window/tab capture, file selection, clipboard paste, drag-and-drop, full-size image preview/download, and removal. Up to five PNG/JPEG/WebP images are allowed (4 MB each, 12 MB total). Images are reviewed in the dialog before submission. Optional contact email and messages up to 5,000 characters are supported. Draft text and images remain on failure; Ctrl/Cmd+Enter submits.

**What will be sent** shows product/version, page, viewport, timezone, user agent, network status, recent JavaScript errors, and a bounded reproduction record: recent UI actions, request URLs/status/timings, control states, scroll position, language, and connection type. Query values, resume handles, job IDs in API paths, and credential patterns are redacted. Request/response bodies, cookies, and password field values are never collected. Activity metadata is retained in this browser tab for up to 15 minutes; screenshots and messages stay in memory until submission or page closure. Screenshots may contain visible candidate information, so the dialog asks the reporter to review and remove private content.

Set `GITHUB_FEEDBACK_TOKEN` in Railway to a fine-grained token limited to this repository with **Issues: Read and write** and **Contents: Read and write**. The token stays on the server. Screenshots are stored under `.github/feedback-attachments/` on the separate `feedback-attachments` branch, then embedded in the issue. Content hashes avoid duplicate image uploads on retry. This branch does not change `main` or trigger its automatic deployment. If screenshot upload fails, no issue is created; an issue-submission timeout tells the reporter to check for an existing issue before retrying. Successfully uploaded images can remain on the attachment branch if a later issue request fails.

The shared widget's bundled screenshot renderer retains its MIT license in `static/vendor/modern-screenshot.LICENSE`. No Nolizi user data, screenshots, or credentials are included.

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
| `GITHUB_FEEDBACK_TOKEN` | Repository-scoped token with Issues and Contents write access | Yes for feedback submission and screenshots |

## Version

Current version: 1.2.0

## Changelog

### v1.2.0
- Add "Show only open positions" checkbox filter (enabled by default)
- Jobs dropdown shows only open positions when filter is active
- Uncheck to see all jobs with status indicator

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
