"""
LampsPlus File Validation Application
Flask-based SFTP file validation system
"""

import os
import io
import zipfile
import csv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import paramiko
import pandas as pd

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generate random secret key for sessions

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
