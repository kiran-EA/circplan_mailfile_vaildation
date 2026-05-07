# LampsPlus File Validation System

A Flask-based web application for validating catalog mail files from LampsPlus SFTP server.

## Features

- 🔐 Secure session-based authentication
- 📁 Live SFTP connection to LampsPlus server
- 📦 ZIP file extraction and header display
- 📊 Multiple file selection and batch processing
- 🎨 Modern, responsive UI with Google Fonts
- 🔒 CSRF protection and secure headers

## Tech Stack

**Backend:**
- Python 3.x
- Flask (serverless-ready for Vercel)
- paramiko (SFTP/SSH)
- pandas/numpy (data processing)

**Frontend:**
- Vanilla HTML/CSS/JavaScript
- Google Fonts (JetBrains Mono, Syne, Inter)

**Authentication:**
- Flask session-based auth (signed cookies)
- Cache-Control headers for logout protection

## Installation & Setup

### 1. Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Project Structure

```
lampsplus-validation/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── keys/
│   └── lp_key            # SSH private key (OpenSSH format)
├── static/
│   ├── css/
│   │   └── style.css     # Main stylesheet
│   └── js/
│       ├── login.js      # Login page JavaScript
│       └── dashboard.js  # Dashboard JavaScript
├── templates/
│   ├── login.html        # Login page template
│   └── dashboard.html    # Dashboard template
└── temp/                 # Temporary directory for file processing
```

### 4. Running the Application

**Local Development:**

```bash
python app.py
```

The application will start on `http://localhost:5000`

**Access the application:**
- Navigate to `http://localhost:5000`
- Login with credentials:
  - Username: `directmarketing`
  - Password: `Lampsplus!1901`

## Usage Guide

### Mail File Validation

1. **Login** to the application
2. Click on **"Mail File Validation"** tab
3. Click **"Load Files from SFTP"** button
   - Connects to: `ftp1.lampsplus.com:9822`
   - Directory: `/FromLP/Catalog Mail Files`
4. **Select files** from the list (multiple selection supported)
5. Click **"Proceed"** to process selected files
6. View **extracted headers** and file information

### CircPlan Validation

*Coming Soon* - This feature is under development

## SFTP Configuration

The application connects to LampsPlus SFTP server with these settings:

- **Host:** ftp1.lampsplus.com
- **Port:** 9822
- **Username:** ExpressAnalytic
- **Authentication:** SSH Key (`keys/lp_key`)

## Security Features

- Session-based authentication with secure cookies
- CSRF protection
- `Cache-Control: no-store` headers to prevent caching
- `pageshow` event handling for bfcache protection
- SSH key-based SFTP authentication
- Auto-logout on browser back/forward navigation

## File Processing

The application:
1. Lists all files from the SFTP directory
2. Downloads selected ZIP files to memory (not disk)
3. Extracts and parses CSV/TXT files inside ZIP archives
4. Displays first row (header) with column names
5. Shows total row count for each file
6. Temporarily stores unzipped content (auto-cleanup)

**Supported file formats inside ZIP:**
- CSV (comma-delimited)
- TXT (comma-delimited)

**Expected header format:**
- "CustNo","Keycode",... (quoted columns)
- Delimiter: comma (,)

## Development Notes

### Running in VS Code

1. Open the project folder in VS Code
2. Open integrated terminal (Ctrl + `)
3. Install dependencies: `pip install -r requirements.txt`
4. Run: `python app.py`
5. Open browser to `http://localhost:5000`

### Debugging

- Flask debug mode is enabled by default in `app.py`
- Check console for error messages
- SFTP connection errors will display in the UI

## Deployment to Vercel (Future)

To deploy to Vercel:

1. Create `vercel.json` configuration
2. Update `app.py` for serverless functions
3. Set environment variables for SSH key
4. Configure build settings

*(Deployment guide will be added when needed)*

## Troubleshooting

**SFTP Connection Issues:**
- Verify SSH key permissions: `chmod 600 keys/lp_key`
- Check network connectivity to `ftp1.lampsplus.com:9822`
- Ensure SSH key is in correct OpenSSH format

**File Processing Errors:**
- Verify ZIP files contain valid CSV/TXT files
- Check file encoding (UTF-8 expected)
- Ensure files have proper header rows

**Login Issues:**
- Clear browser cookies
- Check username/password credentials
- Verify session secret key is set

## License

Internal use only - LampsPlus

## Support

For issues or questions, contact: kiran-EA

---

**Version:** 1.0.0  
**Last Updated:** April 29, 2026
