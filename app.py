"""
LampsPlus File Validation Application
Flask-based SFTP file validation system
"""

import os
import io
import zipfile
import csv
import uuid
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, stream_with_context
import json
import paramiko
import pandas as pd

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# In-memory job store: {job_id: {'status': 'running'|'done'|'error', 'results': [...], 'progress': 'msg'}}
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

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


def get_sftp_connection() -> Tuple[paramiko.SSHClient, paramiko.SFTPClient]:
    """Establish SFTP connection using SSH key"""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        key_content = os.environ.get('SFTP_PRIVATE_KEY')
        if key_content:
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

        transport = ssh.get_transport()
        if transport:
            transport.set_keepalive(30)
            transport.window_size = 4 * 1024 * 1024
            transport.packetizer.REKEY_BYTES = pow(2, 40)

        sftp = ssh.open_sftp()
        sftp.get_channel().settimeout(300)
        return ssh, sftp
    except Exception as e:
        logger.error(f"SFTP Connection Error: {str(e)}")
        raise Exception(f"SFTP Connection Error: {str(e)}")


def list_sftp_files(remote_path: str) -> Dict[str, Any]:
    """List all files from SFTP directory"""
    ssh, sftp = None, None
    try:
        ssh, sftp = get_sftp_connection()
        file_list = sftp.listdir(remote_path)
        files = []
        for filename in file_list:
            try:
                file_stat = sftp.stat(f"{remote_path}/{filename}")
                files.append({
                    'name': filename,
                    'size': file_stat.st_size,
                    'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
            except:
                files.append({'name': filename, 'size': 0, 'modified': 'N/A'})
        return {'files': sorted(files, key=lambda x: x['name'])}
    except Exception as e:
        logger.error(f"Error listing files from {remote_path}: {str(e)}")
        return {'error': str(e)}
    finally:
        if sftp: sftp.close()
        if ssh: ssh.close()


def download_and_process_file(remote_path: str, filename: str, retries: int = 3) -> Dict[str, Any]:
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
            last_error = str(e)
            logger.warning(f"[Attempt {attempt}/{retries}] Error processing {filename}: {last_error}")
        finally:
            if sftp: sftp.close()
            if ssh: ssh.close()

    return {'error': f'Download Error (after {retries} attempts): {last_error}'}


EXPECTED_COLUMNS = [
    'CustNo', 'Keycode', 'Name', 'Company', 'Address3', 'Address2',
    'Address1', 'City', 'State', 'ZIP', 'Message1', 'Message2',
    'Message3', 'Message4', 'Message5', 'Message6', 'Message7', 'Message8',
    'Message9', 'Message10', 'ORGRecNo', 'RecNo', 'File'
]


def detect_delimiter(line: str) -> str:
    """Detect delimiter from a header line"""
    candidates = [('|', line.count('|')), (',', line.count(',')),
                  ('\t', line.count('\t')), (';', line.count(';'))]
    best = max(candidates, key=lambda x: x[1])
    return best[0] if best[1] > 0 else ','


def process_zip_file(file_data: io.BytesIO, zip_filename: str) -> Dict[str, Any]:
    """Extract and read headers from ZIP file"""
    try:
        results = []
        with zipfile.ZipFile(file_data, 'r') as zip_ref:
            for file_name in zip_ref.namelist():
                if file_name.endswith('/') or file_name.startswith('.'): continue
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

                        columns_valid = header == EXPECTED_COLUMNS

                        custno_null_pct = None
                        keycode_null_pct = None
                        data_rows = len(lines) - 1

                        if data_rows > 0 and header:
                            custno_idx = header.index('CustNo') if 'CustNo' in header else None
                            keycode_idx = header.index('Keycode') if 'Keycode' in header else None
                            custno_null = 0
                            keycode_null = 0
                            for line in lines[1:]:
                                row_reader = csv.reader([line], delimiter=delimiter)
                                try:
                                    row = next(row_reader)
                                    if custno_idx is not None and (custno_idx >= len(row) or row[custno_idx].strip() == ''):
                                        custno_null += 1
                                    if keycode_idx is not None and (keycode_idx >= len(row) or row[keycode_idx].strip() == ''):
                                        keycode_null += 1
                                except StopIteration: continue

                            custno_null_pct = round(custno_null / data_rows * 100, 2) if custno_idx is not None else None
                            keycode_null_pct = round(keycode_null / data_rows * 100, 2) if keycode_idx is not None else None

                        results.append({
                            'filename': file_name,
                            'header': header,
                            'row_count': len(lines),
                            'delimiter': delimiter,
                            'columns_valid': columns_valid,
                            'custno_null_pct': custno_null_pct,
                            'keycode_null_pct': keycode_null_pct,
                            'status': 'success'
                        })
                    except Exception as e:
                        results.append({'filename': file_name, 'header': [], 'row_count': 0, 'status': f'error: {str(e)}'})
        return {'zip_file': zip_filename, 'files': results}
    except Exception as e:
        logger.error(f"ZIP Processing Error for {zip_filename}: {str(e)}")
        return {'error': f'ZIP Processing Error: {str(e)}'}


# ... (Keep existing Flask routes)

@app.route('/api/server/exec', methods=['POST'])
def api_server_exec():
    if 'logged_in' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    data = request.json or {}
    cmd = data.get('cmd', '').strip()
    if not cmd:
        return jsonify({'error': 'No command'}), 400

    # Allowlist of commands for safety
    allowed_commands = ['ls', 'cat', 'grep', 'find', 'tail', 'head', 'ps', 'df', 'free', 'date', 'pwd']
    if not any(cmd.split()[0] == c for c in allowed_commands):
        return jsonify({'error': 'Command not allowed'}), 403

    try:
        ssh = _ssh_connect()
        _, stdout, stderr = ssh.exec_command(cmd, timeout=30)
        out = stdout.read().decode(errors='replace')
        err = stderr.read().decode(errors='replace')
        ssh.close()
        return jsonify({'output': out + (('\n[stderr]: ' + err) if err.strip() else '')})
    except Exception as e:
        logger.error(f"Server command execution error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ... (Rest of existing code)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9000)
