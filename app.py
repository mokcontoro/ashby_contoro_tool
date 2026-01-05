import os
import io
import json
import zipfile
import requests
import math
import time
import secrets
import threading
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, jsonify, request, send_file, session, redirect, url_for, Response
from dotenv import load_dotenv
from pypdf import PdfReader, PdfWriter

__version__ = '1.2.0'

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

ASHBY_API_KEY = os.getenv('ASHBY_API_KEY')
ASHBY_BASE_URL = 'https://api.ashbyhq.com'
APP_PASSKEY = os.getenv('APP_PASSKEY', 'changeme')


def login_required(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def ashby_request(endpoint, data=None, retries=3):
    """Make an authenticated request to the Ashby API with retry logic."""
    url = f"{ASHBY_BASE_URL}/{endpoint}"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    for attempt in range(retries):
        try:
            response = requests.post(
                url,
                json=data or {},
                auth=(ASHBY_API_KEY, ''),
                headers=headers,
                timeout=30
            )

            # Check for rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 5))
                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            # Check for empty response
            if not response.text:
                if attempt < retries - 1:
                    print(f"Empty response, retrying in 2 seconds... (attempt {attempt + 1})")
                    time.sleep(2)
                    continue
                return {'success': False, 'errors': 'Empty response from API'}

            return response.json()

        except requests.exceptions.JSONDecodeError:
            if attempt < retries - 1:
                print(f"JSON decode error, retrying in 2 seconds... (attempt {attempt + 1})")
                time.sleep(2)
                continue
            return {'success': False, 'errors': 'Invalid JSON response from API'}

        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                print(f"Request error: {e}, retrying in 2 seconds... (attempt {attempt + 1})")
                time.sleep(2)
                continue
            return {'success': False, 'errors': f'Request failed: {str(e)}'}

    return {'success': False, 'errors': 'Max retries exceeded'}


def ashby_request_paginated(endpoint, data=None):
    """Make paginated requests to the Ashby API and return all results."""
    all_results = []
    cursor = None

    while True:
        request_data = data.copy() if data else {}
        if cursor:
            request_data['cursor'] = cursor

        result = ashby_request(endpoint, request_data)

        if not result.get('success'):
            return result  # Return error response

        all_results.extend(result.get('results', []))

        # Check if there's more data
        if result.get('moreDataAvailable') and result.get('nextCursor'):
            cursor = result['nextCursor']
            time.sleep(0.2)  # Small delay between pages to avoid rate limiting
        else:
            break

    return {'success': True, 'results': all_results}


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login."""
    if request.method == 'POST':
        passkey = request.form.get('passkey', '')
        if passkey == APP_PASSKEY:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid passkey')
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Handle logout."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/api/jobs')
@login_required
def get_jobs():
    """Get all jobs from Ashby."""
    result = ashby_request_paginated('job.list')
    if result.get('success'):
        jobs = result.get('results', [])
        # Return simplified job data
        return jsonify([{
            'id': job.get('id'),
            'title': job.get('title'),
            'status': job.get('status'),
            'departmentName': job.get('department', {}).get('name', 'N/A') if job.get('department') else 'N/A',
            'locationName': job.get('location', {}).get('name', 'N/A') if job.get('location') else 'N/A'
        } for job in jobs])
    return jsonify({'error': result.get('errors', 'Unknown error')}), 400


@app.route('/api/jobs/<job_id>/stages')
@login_required
def get_stages(job_id):
    """Get interview stages for a specific job."""
    # First get the job info to find the interview plan
    job_result = ashby_request('job.info', {'id': job_id})

    if not job_result.get('success'):
        return jsonify({'error': 'Failed to get job info'}), 400

    job = job_result.get('results', {})
    interview_plan_id = job.get('defaultInterviewPlanId')

    if not interview_plan_id:
        return jsonify([])

    # Get interview stages for this plan
    stages_result = ashby_request('interviewStage.list', {'interviewPlanId': interview_plan_id})

    if stages_result.get('success'):
        stages = stages_result.get('results', [])
        return jsonify([{
            'id': stage.get('id'),
            'title': stage.get('title'),
            'type': stage.get('type'),
            'orderInInterviewPlan': stage.get('orderInInterviewPlan')
        } for stage in stages])

    return jsonify({'error': stages_result.get('errors', 'Unknown error')}), 400


def fetch_candidate_resume_handle(candidate_id):
    """Fetch resume file handle for a single candidate."""
    if not candidate_id:
        return None
    candidate_result = ashby_request('candidate.info', {'id': candidate_id})
    if candidate_result.get('success'):
        candidate_full = candidate_result.get('results', {})
        resume_handle_obj = candidate_full.get('resumeFileHandle')
        if resume_handle_obj:
            return resume_handle_obj.get('handle')
    return None


@app.route('/api/candidates')
@login_required
def get_candidates():
    """Get candidates for a specific job and stage with SSE progress updates."""
    job_id = request.args.get('jobId')
    stage_id = request.args.get('stageId')

    if not job_id:
        return jsonify({'error': 'Job ID is required'}), 400

    def generate():
        # Send initial status
        yield f"data: {json.dumps({'type': 'status', 'message': 'Fetching applications...'})}\n\n"

        # Get applications filtered by job (server-side)
        filter_params = {'jobId': job_id}
        applications_result = ashby_request_paginated('application.list', filter_params)

        if not applications_result.get('success'):
            yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to get applications'})}\n\n"
            return

        all_apps = applications_result.get('results', [])

        yield f"data: {json.dumps({'type': 'status', 'message': f'Found {len(all_apps)} applications. Filtering by stage...'})}\n\n"

        # Filter by stage (client-side, as Ashby API doesn't support stage filter)
        if stage_id:
            filtered_apps = [app for app in all_apps
                            if app.get('currentInterviewStage', {}).get('id') == stage_id]
        else:
            filtered_apps = all_apps
        total_candidates = len(filtered_apps)

        yield f"data: {json.dumps({'type': 'status', 'message': f'Found {total_candidates} candidates in selected stage. Fetching resume info...'})}\n\n"

        # Build basic candidate info first
        candidates = []
        candidate_ids = []
        for app_data in filtered_apps:
            candidate_basic = app_data.get('candidate', {})
            candidate_id = candidate_basic.get('id')
            candidate_ids.append(candidate_id)
            candidates.append({
                'id': candidate_id,
                'name': candidate_basic.get('name'),
                'email': candidate_basic.get('primaryEmailAddress', {}).get('value', 'N/A') if candidate_basic.get('primaryEmailAddress') else 'N/A',
                'applicationId': app_data.get('id'),
                'stage': app_data.get('currentInterviewStage', {}).get('title', 'N/A') if app_data.get('currentInterviewStage') else 'N/A',
                'appliedAt': app_data.get('createdAt'),
                'resumeFileHandle': None
            })

        # Fetch resume handles concurrently with progress tracking
        if candidate_ids:
            completed_count = 0
            lock = threading.Lock()

            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_idx = {
                    executor.submit(fetch_candidate_resume_handle, cid): idx
                    for idx, cid in enumerate(candidate_ids)
                }
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        resume_handle = future.result()
                        candidates[idx]['resumeFileHandle'] = resume_handle
                    except Exception as e:
                        print(f"Error fetching candidate {candidate_ids[idx]}: {e}")

                    with lock:
                        completed_count += 1
                        if completed_count % 10 == 0 or completed_count == total_candidates:
                            progress = int((completed_count / total_candidates) * 100)
                            yield f"data: {json.dumps({'type': 'progress', 'current': completed_count, 'total': total_candidates, 'percent': progress})}\n\n"

        # Send final result
        yield f"data: {json.dumps({'type': 'complete', 'candidates': candidates})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/download-resume/<file_handle>')
@login_required
def download_resume(file_handle):
    """Download a single resume file."""
    # Get file URL from Ashby
    file_result = ashby_request('file.info', {'fileHandle': file_handle})

    if not file_result.get('success'):
        return jsonify({'error': 'Failed to get file info'}), 400

    file_info = file_result.get('results', {})
    file_url = file_info.get('url')
    filename = file_info.get('name', 'resume.pdf')

    if not file_url:
        return jsonify({'error': 'No file URL available'}), 400

    # Download the file
    response = requests.get(file_url)
    if response.status_code != 200:
        return jsonify({'error': 'Failed to download file'}), 400

    return send_file(
        io.BytesIO(response.content),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


@app.route('/api/download-bulk', methods=['POST'])
@login_required
def download_bulk():
    """Download multiple resumes as a ZIP file."""
    data = request.json
    file_handles = data.get('fileHandles', [])
    candidate_names = data.get('candidateNames', [])

    if not file_handles:
        return jsonify({'error': 'No file handles provided'}), 400

    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, file_handle in enumerate(file_handles):
            try:
                # Get file URL from Ashby
                file_result = ashby_request('file.info', {'fileHandle': file_handle})

                if not file_result.get('success'):
                    continue

                file_info = file_result.get('results', {})
                file_url = file_info.get('url')
                original_filename = file_info.get('name', 'resume.pdf')

                if not file_url:
                    continue

                # Download the file
                response = requests.get(file_url)
                if response.status_code != 200:
                    continue

                # Create filename with candidate name
                candidate_name = candidate_names[i] if i < len(candidate_names) else f'candidate_{i}'
                # Sanitize filename
                safe_name = "".join(c for c in candidate_name if c.isalnum() or c in (' ', '-', '_')).strip()

                # Get file extension from original filename
                ext = os.path.splitext(original_filename)[1] or '.pdf'
                filename = f"{safe_name}{ext}"

                # Add to ZIP
                zip_file.writestr(filename, response.content)

            except Exception as e:
                print(f"Error downloading file {file_handle}: {e}")
                continue

    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='candidate_resumes.zip'
    )


@app.route('/pdf-combiner')
@login_required
def pdf_combiner():
    """Serve the PDF combiner page."""
    return render_template('pdf_combiner.html')


@app.route('/api/combine-pdfs', methods=['POST'])
@login_required
def combine_pdfs():
    """Combine PDFs from a ZIP file into groups."""
    if 'zipfile' not in request.files:
        return jsonify({'error': 'No ZIP file provided'}), 400

    zip_file = request.files['zipfile']
    pdfs_per_file = int(request.form.get('pdfsPerFile', 10))

    if pdfs_per_file < 1:
        return jsonify({'error': 'PDFs per file must be at least 1'}), 400

    try:
        # Read the ZIP file
        zip_buffer = io.BytesIO(zip_file.read())
        pdf_files = []

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            # Get all PDF files from the ZIP, sorted by name
            pdf_names = sorted([
                name for name in zf.namelist()
                if name.lower().endswith('.pdf') and not name.startswith('__MACOSX')
            ])

            if len(pdf_names) == 0:
                return jsonify({'error': 'No PDF files found in the ZIP'}), 400

            # Read all PDF files
            for pdf_name in pdf_names:
                try:
                    pdf_data = zf.read(pdf_name)
                    pdf_files.append({
                        'name': os.path.basename(pdf_name),
                        'data': pdf_data
                    })
                except Exception as e:
                    print(f"Error reading {pdf_name}: {e}")
                    continue

        if len(pdf_files) == 0:
            return jsonify({'error': 'Could not read any PDF files from the ZIP'}), 400

        # Calculate number of output files
        num_output_files = math.ceil(len(pdf_files) / pdfs_per_file)

        # Create output ZIP with combined PDFs
        output_zip_buffer = io.BytesIO()

        with zipfile.ZipFile(output_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as output_zip:
            for i in range(num_output_files):
                start_idx = i * pdfs_per_file
                end_idx = min((i + 1) * pdfs_per_file, len(pdf_files))
                batch = pdf_files[start_idx:end_idx]

                # Combine PDFs in this batch
                pdf_writer = PdfWriter()

                for pdf_item in batch:
                    try:
                        pdf_reader = PdfReader(io.BytesIO(pdf_item['data']))
                        for page in pdf_reader.pages:
                            pdf_writer.add_page(page)
                    except Exception as e:
                        print(f"Error processing {pdf_item['name']}: {e}")
                        continue

                # Write combined PDF to buffer
                combined_buffer = io.BytesIO()
                pdf_writer.write(combined_buffer)
                combined_buffer.seek(0)

                # Add to output ZIP
                output_filename = f"combined_{i + 1:03d}.pdf"
                output_zip.writestr(output_filename, combined_buffer.read())

        output_zip_buffer.seek(0)

        return send_file(
            output_zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='combined_pdfs.zip'
        )

    except zipfile.BadZipFile:
        return jsonify({'error': 'Invalid ZIP file'}), 400
    except Exception as e:
        return jsonify({'error': f'Error processing files: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
