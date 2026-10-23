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

Signed-in users can open **Feedback** from either tool to report bugs, request features, or share general feedback. Reports target only `mokcontoro/ashby_contoro_tool` on GitHub. This repository is public; the dialog shows a public-sharing notice, requires acknowledgement, and previews the report before submission.

By default, **Continue on GitHub** prepares a draft and offers a link to the prefilled issue. The user signs into GitHub and submits it there. No report is marked as submitted just because a draft was prepared. Optional screenshots can be attached on GitHub after reviewing them for private information.

For direct in-app submission, configure `GITHUB_FEEDBACK_TOKEN` in Railway with a dedicated fine-grained GitHub token limited to this repository and **Issues: Read and write**. The token stays on the server; never put it in the repository or frontend. Without it, the GitHub draft flow remains available. Direct submissions return the created issue link; failed requests retain the draft and timeouts prompt the user to check for an existing issue before retrying.

Optional automatic context is limited to the app version and active tool, shown before submission. Candidate details, resume files, URLs, browser history, and console logs are not collected. There is no automatic screenshot capture or local persistent draft storage.

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
| `GITHUB_FEEDBACK_TOKEN` | Repository-scoped token for direct GitHub feedback submission | No (uses prefilled GitHub drafts otherwise) |

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
