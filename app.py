"""
LampsPlus File Validation Application
Flask-based SFTP file validation system
"""

import os
import io
import zipfile
import csv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, stream_with_context
import json
import paramiko
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'lampsplus-local-dev-key-2026')

# Configuration
SFTP_CONFIG = {
    'hostname': 'ftp1.lampsplus.com',
    'port': 9822,
    'username': 'ExpressAnalytic',
    'key_path': os.path.join(os.path.dirname(__file__), 'keys', 'lp_key')
}

# Authentication credentials
VALID_CREDENTIALS = {
    'username': 'directmarketing',
    'password': 'Lampsplus!1901'
}

TEMP_DIR = os.path.join(os.path.dirname(__file__), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)


def get_sftp_connection():
    """Establish SFTP connection using SSH key"""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Load key from env variable (Vercel) or fall back to local file
        key_content = os.environ.get('SFTP_PRIVATE_KEY')
        if key_content:
            # Vercel may store newlines as literal \n — normalize them
            key_content = key_content.replace('\\n', '\n')
            private_key = paramiko.RSAKey.from_private_key(io.StringIO(key_content))
        else:
            private_key = paramiko.RSAKey.from_private_key_file(SFTP_CONFIG['key_path'])

        ssh.connect(
            hostname=SFTP_CONFIG['hostname'],
            port=SFTP_CONFIG['port'],
            username=SFTP_CONFIG['username'],
            pkey=private_key,
            look_for_keys=False,
            allow_agent=False,
            banner_timeout=60,
            auth_timeout=60,
            timeout=60
        )

        # Send keepalive every 30s to prevent connection drops on large files
        transport = ssh.get_transport()
        transport.set_keepalive(30)
        transport.window_size = 4 * 1024 * 1024       # 4 MB window
        transport.packetizer.REKEY_BYTES = pow(2, 40)  # disable rekey during transfer

        sftp = ssh.open_sftp()
        sftp.get_channel().settimeout(300)  # 5 min timeout per operation
        return ssh, sftp
    except Exception as e:
        raise Exception(f"SFTP Connection Error: {str(e)}")


def list_sftp_files(remote_path):
    """List all files from SFTP directory"""
    try:
        ssh, sftp = get_sftp_connection()
        
        # List directory
        files = []
        try:
            file_list = sftp.listdir(remote_path)
            for filename in file_list:
                try:
                    file_stat = sftp.stat(f"{remote_path}/{filename}")
                    files.append({
                        'name': filename,
                        'size': file_stat.st_size,
                        'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
                except:
                    # If stat fails, just add the filename
                    files.append({
                        'name': filename,
                        'size': 0,
                        'modified': 'N/A'
                    })
        except FileNotFoundError:
            return {'error': f'Directory not found: {remote_path}'}
        finally:
            sftp.close()
            ssh.close()
        
        return {'files': sorted(files, key=lambda x: x['name'])}
    except Exception as e:
        return {'error': str(e)}


def download_and_process_file(remote_path, filename, retries=3):
    """Download file from SFTP and process it, with retry on connection drop"""
    last_error = None
    for attempt in range(1, retries + 1):
        ssh, sftp = None, None
        try:
            ssh, sftp = get_sftp_connection()
            remote_file_path = f"{remote_path}/{filename}"
            file_data = io.BytesIO()
            sftp.getfo(remote_file_path, file_data)
            file_data.seek(0)

            if filename.lower().endswith('.zip'):
                return process_zip_file(file_data, filename)
            else:
                return {'error': 'Only ZIP files are supported'}

        except Exception as e:
            import traceback
            last_error = str(e)
            log_path = os.path.join(os.path.dirname(__file__), 'sftp_error.log')
            with open(log_path, 'a') as lf:
                lf.write(f"[Attempt {attempt}/{retries}] {filename}: {last_error}\n")
                traceback.print_exc(file=lf)
        finally:
            try:
                if sftp: sftp.close()
                if ssh: ssh.close()
            except Exception:
                pass

    return {'error': f'Download Error (after {retries} attempts): {last_error}'}


EXPECTED_COLUMNS = [
    'CustNo', 'Keycode', 'Name', 'Company', 'Address3', 'Address2',
    'Address1', 'City', 'State', 'ZIP', 'Message1', 'Message2',
    'Message3', 'Message4', 'Message5', 'Message6', 'Message7', 'Message8',
    'Message9', 'Message10', 'ORGRecNo', 'RecNo', 'File'
]


def detect_delimiter(line):
    """Detect delimiter from a header line"""
    candidates = [('|', line.count('|')), (',', line.count(',')),
                  ('\t', line.count('\t')), (';', line.count(';'))]
    best = max(candidates, key=lambda x: x[1])
    return best[0] if best[1] > 0 else ','


def process_zip_file(file_data, zip_filename):
    """Extract and read headers from ZIP file"""
    try:
        results = []

        with zipfile.ZipFile(file_data, 'r') as zip_ref:
            file_list = zip_ref.namelist()

            for file_name in file_list:
                if file_name.endswith('/') or file_name.startswith('.'):
                    continue

                with zip_ref.open(file_name) as f:
                    content = f.read()

                    try:
                        text_content = content.decode('utf-8')
                        lines = text_content.strip().split('\n')

                        if not lines:
                            results.append({'filename': file_name, 'header': [], 'row_count': 0, 'status': 'error: empty file'})
                            continue

                        header_line = lines[0]
                        delimiter = detect_delimiter(header_line)

                        reader = csv.reader([header_line], delimiter=delimiter)
                        header = [col.strip() for col in next(reader)]

                        # Column name validation
                        columns_valid = header == EXPECTED_COLUMNS

                        # Null % for CustNo and Keycode
                        custno_null_pct = None
                        keycode_null_pct = None
                        data_rows = len(lines) - 1  # exclude header

                        if data_rows > 0 and header:
                            custno_idx = header.index('CustNo') if 'CustNo' in header else None
                            keycode_idx = header.index('Keycode') if 'Keycode' in header else None

                            custno_null = 0
                            keycode_null = 0

                            for line in lines[1:]:
                                row_reader = csv.reader([line], delimiter=delimiter)
                                try:
                                    row = next(row_reader)
                                except StopIteration:
                                    continue
                                if custno_idx is not None:
                                    val = row[custno_idx].strip() if custno_idx < len(row) else ''
                                    if val == '':
                                        custno_null += 1
                                if keycode_idx is not None:
                                    val = row[keycode_idx].strip() if keycode_idx < len(row) else ''
                                    if val == '':
                                        keycode_null += 1

                            custno_null_pct = round(custno_null / data_rows * 100, 2) if custno_idx is not None else None
                            keycode_null_pct = round(keycode_null / data_rows * 100, 2) if keycode_idx is not None else None

                        delimiter_display = {
                            '|': 'Pipe (|)', ',': 'Comma (,)',
                            '\t': 'Tab', ';': 'Semicolon (;)'
                        }.get(delimiter, delimiter)

                        results.append({
                            'filename': file_name,
                            'header': header,
                            'row_count': len(lines),
                            'delimiter': delimiter_display,
                            'columns_valid': columns_valid,
                            'custno_null_pct': custno_null_pct,
                            'keycode_null_pct': keycode_null_pct,
                            'status': 'success'
                        })
                    except Exception as e:
                        results.append({
                            'filename': file_name,
                            'header': [],
                            'row_count': 0,
                            'status': f'error: {str(e)}'
                        })

        return {
            'zip_file': zip_filename,
            'files': results
        }
    except Exception as e:
        return {'error': f'ZIP Processing Error: {str(e)}'}


# ==================== ROUTES ====================

@app.route('/')
def index():
    """Redirect to login page"""
    if 'logged_in' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication"""
    if request.method == 'POST':
        data = request.json
        username = data.get('username', '')
        password = data.get('password', '')
        
        if (username == VALID_CREDENTIALS['username'] and 
            password == VALID_CREDENTIALS['password']):
            session['logged_in'] = True
            session['username'] = username
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid credentials'})
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
def dashboard():
    """Main dashboard page"""
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session.get('username'))


@app.route('/api/list-files')
def api_list_files():
    """API endpoint to list SFTP files"""
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    remote_path = request.args.get('path', '/FromLP/Catalog Mail Files')
    result = list_sftp_files(remote_path)
    return jsonify(result)


@app.route('/api/process-files', methods=['POST'])
def api_process_files():
    """API endpoint to process selected files"""
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.json
    files = data.get('files', [])
    remote_path = data.get('path', '/FromLP/Catalog Mail Files')

    results = []
    for filename in files:
        result = download_and_process_file(remote_path, filename)
        results.append(result)

    return jsonify({'results': results})


# ==================== CIRCPLAN ROUTES ====================

CIRCPLAN_EXPECTED_COLUMNS = [
    'Key Code', 'SegKey', 'Customer Type', 'List Name', 'Rec', '$',
    'FREQ', 'Version Type', 'Broker', 'OPT 1', 'OPT 2', 'OPT3',
    'Gross Qty', 'Quantity Mailed', 'LIST COST', 'Sub-Category',
    'Campaign_Name', 'Start_Date', 'End_Date'
]

CIRCPLAN_SERVER = {
    'hostname': '54.176.67.86',
    'port': 22,
    'username': 'eapcprod',
    'password': '6trKdbLw',
    'script_dir': '/app/share/Informatica/scripts/bin/CircPlan',
    'script': 'circ_plan_load_new_v2.sh'
}


def _parse_circplan_content(content_bytes, filename):
    """Parse a CircPlan CSV/TXT content and run QC checks"""
    try:
        try:
            text = content_bytes.decode('utf-8-sig')  # strips BOM if present
        except UnicodeDecodeError:
            text = content_bytes.decode('latin-1')

        lines = [l.rstrip('\r') for l in text.strip().split('\n')]
        if not lines:
            return {'filename': filename, 'header': [], 'row_count': 0, 'status': 'error: empty file'}

        delimiter = detect_delimiter(lines[0])
        reader = csv.reader([lines[0]], delimiter=delimiter)

        def _norm(c):
            # collapse all whitespace variants (including non-breaking space) to single space
            return ' '.join(c.replace('\xa0', ' ').split())

        raw_header = [col.strip() for col in next(reader)]
        header_norm = [_norm(col) for col in raw_header]
        expected_norm = [_norm(col) for col in CIRCPLAN_EXPECTED_COLUMNS]
        columns_valid = header_norm == expected_norm
        header = raw_header  # keep original for display

        # Key Code null %
        keycode_null_pct = None
        data_rows = len(lines) - 1
        kc_key = next((c for c in header if _norm(c) == _norm('Key Code')), None)
        if data_rows > 0 and kc_key:
            kc_idx = header.index(kc_key)
            kc_null = 0
            for line in lines[1:]:
                rdr = csv.reader([line], delimiter=delimiter)
                try:
                    row = next(rdr)
                    if kc_idx >= len(row) or row[kc_idx].strip() == '':
                        kc_null += 1
                except StopIteration:
                    continue
            keycode_null_pct = round(kc_null / data_rows * 100, 2)

        delimiter_display = {
            '|': 'Pipe (|)', ',': 'Comma (,)',
            '\t': 'Tab', ';': 'Semicolon (;)'
        }.get(delimiter, delimiter)

        return {
            'filename': filename,
            'header': header,
            'row_count': len(lines),
            'delimiter': delimiter_display,
            'columns_valid': columns_valid,
            'keycode_null_pct': keycode_null_pct,
            'status': 'success'
        }
    except Exception as e:
        return {'filename': filename, 'header': [], 'row_count': 0, 'status': f'error: {str(e)}'}


def process_circplan_file(file_data, filename):
    """Extract and QC a CircPlan file (ZIP or direct CSV/TXT)"""
    try:
        content_bytes = file_data.read()

        if zipfile.is_zipfile(io.BytesIO(content_bytes)):
            results = []
            with zipfile.ZipFile(io.BytesIO(content_bytes), 'r') as zf:
                for inner in zf.namelist():
                    if inner.endswith('/') or inner.startswith('.'):
                        continue
                    with zf.open(inner) as f:
                        results.append(_parse_circplan_content(f.read(), inner))
            return {'zip_file': filename, 'files': results}

        return {'zip_file': filename, 'files': [_parse_circplan_content(content_bytes, filename)]}
    except Exception as e:
        return {'error': f'Processing Error: {str(e)}'}


def circplan_download_and_process(filename, retries=3):
    """Download and process a CircPlan file from SFTP"""
    remote_path = '/FromLP/Circ Plans'
    last_error = None
    for attempt in range(1, retries + 1):
        ssh, sftp = None, None
        try:
            ssh, sftp = get_sftp_connection()
            file_data = io.BytesIO()
            sftp.getfo(f"{remote_path}/{filename}", file_data)
            file_data.seek(0)
            return process_circplan_file(file_data, filename)
        except Exception as e:
            last_error = str(e)
        finally:
            try:
                if sftp: sftp.close()
                if ssh: ssh.close()
            except Exception:
                pass
    return {'error': f'Download Error (after {retries} attempts): {last_error}'}


@app.route('/api/circplan/list-files')
def api_circplan_list_files():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    result = list_sftp_files('/FromLP/Circ Plans')
    return jsonify(result)


@app.route('/api/circplan/process-files', methods=['POST'])
def api_circplan_process_files():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json
    files = data.get('files', [])
    results = [circplan_download_and_process(f) for f in files]
    return jsonify({'results': results})


@app.route('/api/circplan/start-script', methods=['POST'])
def api_circplan_start_script():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    session['cp_script_params'] = request.json
    return jsonify({'ok': True})


@app.route('/api/circplan/stream')
def api_circplan_stream():
    if 'logged_in' not in session:
        return Response('data: {"line":"Not authenticated","done":true}\n\n',
                        content_type='text/event-stream')

    params = session.get('cp_script_params', {})
    camp_name    = params.get('camp_name', '').strip()
    is_ntf       = params.get('is_ntf', 'n').strip()
    keycode_file = params.get('keycode_file', '').strip()
    zip_type     = params.get('zip_type', 'combined').strip()
    mail_file    = params.get('mail_file', '').strip()
    mail_files   = params.get('mail_files', '').strip()

    # Build all stdin inputs (initial prompts + 'y' for any mid-script confirmations)
    mail_input = mail_file if zip_type == 'combined' else mail_files
    stdin_inputs = '\n'.join([camp_name, is_ntf, keycode_file, zip_type,
                               mail_input, 'y', 'y', 'y', 'y']) + '\n'

    def generate():
        ssh = None
        try:
            yield f"data: {json.dumps({'line': '--- Connecting to server 54.176.67.86 ...'})}\n\n"
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(CIRCPLAN_SERVER['hostname'], port=CIRCPLAN_SERVER['port'],
                        username=CIRCPLAN_SERVER['username'],
                        password=CIRCPLAN_SERVER['password'], timeout=30)

            yield f"data: {json.dumps({'line': '--- Connected. Launching script...'})}\n\n"

            cmd = (f"cd {CIRCPLAN_SERVER['script_dir']} && "
                   f"sh {CIRCPLAN_SERVER['script']}")
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=3600)
            stdin.write(stdin_inputs)
            stdin.channel.shutdown_write()

            for line in iter(stdout.readline, ''):
                if line:
                    yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
            for line in iter(stderr.readline, ''):
                if line:
                    yield f"data: {json.dumps({'line': '[ERR] ' + line.rstrip()})}\n\n"

            exit_code = stdout.channel.recv_exit_status()
            status = 'completed successfully' if exit_code == 0 else f'exited with code {exit_code}'
            yield f"data: {json.dumps({'line': f'--- Script {status}', 'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'ERROR: {str(e)}', 'done': True})}\n\n"
        finally:
            if ssh:
                try: ssh.close()
                except: pass

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/mailfile/start-script', methods=['POST'])
def api_mailfile_start_script():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    session['mf_script_params'] = request.json
    return jsonify({'ok': True})


@app.route('/api/mailfile/stream')
def api_mailfile_stream():
    if 'logged_in' not in session:
        return Response('data: {"line":"Not authenticated","done":true}\n\n',
                        content_type='text/event-stream')

    params    = session.get('mf_script_params', {})
    camp_name = params.get('camp_name', '').strip()

    def generate():
        ssh = None
        try:
            yield f"data: {json.dumps({'line': '--- Connecting to server 54.176.67.86 ...'})}\n\n"
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(CIRCPLAN_SERVER['hostname'], port=CIRCPLAN_SERVER['port'],
                        username=CIRCPLAN_SERVER['username'],
                        password=CIRCPLAN_SERVER['password'], timeout=30)

            yield f"data: {json.dumps({'line': '--- Connected. Launching mail_file_load.sh ...'})}\n\n"

            cmd = (f"cd {CIRCPLAN_SERVER['script_dir']} && "
                   f"export camp_name={camp_name!r} && sh mail_file_load.sh")
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=3600)
            stdin.channel.shutdown_write()

            for line in iter(stdout.readline, ''):
                if line:
                    yield f"data: {json.dumps({'line': line.rstrip()})}\n\n"
            for line in iter(stderr.readline, ''):
                if line:
                    yield f"data: {json.dumps({'line': '[ERR] ' + line.rstrip()})}\n\n"

            exit_code = stdout.channel.recv_exit_status()
            status = 'completed successfully' if exit_code == 0 else f'exited with code {exit_code}'
            yield f"data: {json.dumps({'line': f'--- Script {status}', 'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'ERROR: {str(e)}', 'done': True})}\n\n"
        finally:
            if ssh:
                try: ssh.close()
                except: pass

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ==================== SERVER TERMINAL ====================

def _ssh_connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(CIRCPLAN_SERVER['hostname'], port=CIRCPLAN_SERVER['port'],
                username=CIRCPLAN_SERVER['username'],
                password=CIRCPLAN_SERVER['password'], timeout=15)
    return ssh


@app.route('/server-terminal')
def server_terminal():
    if 'logged_in' not in session:
        return redirect(url_for('login'))
    return render_template('server_terminal.html', username=session.get('username', ''))


@app.route('/api/server/ls')
def api_server_ls():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    path = request.args.get('path', '/app/share/Informatica/scripts/bin').strip()
    try:
        ssh = _ssh_connect()
        cmd = f"ls -la {path!r} 2>&1"
        _, stdout, _ = ssh.exec_command(cmd)
        raw = stdout.read().decode(errors='replace')
        ssh.close()

        entries = []
        for line in raw.splitlines():
            if line.startswith('total') or not line.strip():
                continue
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            perms, _, _, _, size, month, day, time_or_year, name = parts
            is_dir = perms.startswith('d')
            is_hidden = name.startswith('.')
            entries.append({
                'name': name,
                'is_dir': is_dir,
                'is_hidden': is_hidden,
                'size': size,
                'modified': f"{month} {day} {time_or_year}",
                'perms': perms,
            })
        return jsonify({'path': path, 'entries': entries})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/server/cat')
def api_server_cat():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    path = request.args.get('path', '').strip()
    if not path:
        return jsonify({'error': 'No path provided'}), 400
    try:
        ssh = _ssh_connect()
        _, stdout, stderr = ssh.exec_command(f"cat {path!r} 2>&1 | head -500")
        content = stdout.read().decode(errors='replace')
        ssh.close()
        return jsonify({'path': path, 'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/server/search')
def api_server_search():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    base = request.args.get('path', '/app/share/Informatica/scripts/bin').strip()
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': 'No search query'}), 400
    try:
        ssh = _ssh_connect()
        cmd = f"find {base!r} -maxdepth 3 -name {('*'+query+'*')!r} 2>/dev/null | head -100"
        _, stdout, _ = ssh.exec_command(cmd)
        results = [l.strip() for l in stdout.read().decode(errors='replace').splitlines() if l.strip()]
        ssh.close()
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/server/exec', methods=['POST'])
def api_server_exec():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json or {}
    cmd = data.get('cmd', '').strip()
    if not cmd:
        return jsonify({'error': 'No command'}), 400
    # block destructive commands
    blocked = ['rm ', 'rmdir', 'mkfs', '> /', 'dd if', 'chmod 777 /', 'chown']
    if any(b in cmd for b in blocked):
        return jsonify({'error': 'Command blocked for safety'}), 403
    try:
        ssh = _ssh_connect()
        _, stdout, stderr = ssh.exec_command(cmd, timeout=30)
        out = stdout.read().decode(errors='replace')
        err = stderr.read().decode(errors='replace')
        ssh.close()
        return jsonify({'output': out + (('\n[stderr]: ' + err) if err.strip() else '')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Set response headers for security
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9000)
