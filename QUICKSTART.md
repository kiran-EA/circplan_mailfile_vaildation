# Quick Start Guide
## LampsPlus File Validation System

### 🚀 Getting Started in 3 Steps

#### Step 1: Extract the ZIP file
Unzip `lampsplus-validation.zip` to your desired location.

#### Step 2: Install Dependencies
Open terminal/command prompt in the project folder and run:

**Windows:**
```cmd
pip install -r requirements.txt
```

**Mac/Linux:**
```bash
pip install -r requirements.txt
```

#### Step 3: Run the Application

**Windows:**
- Double-click `run.bat`
- OR in terminal: `python app.py`

**Mac/Linux:**
- In terminal: `./run.sh`
- OR: `python app.py`

The application will start at: **http://localhost:5000**

---

### 🔑 Login Credentials

```
Username: directmarketing
Password: Lampsplus!1901
```

---

### 📋 Using the Application

1. **Login** with the credentials above
2. Navigate to **"Mail File Validation"** tab
3. Click **"Load Files from SFTP"**
   - This connects to LampsPlus SFTP server
   - Lists all files from `/FromLP/Catalog Mail Files`
4. **Select files** you want to process (checkbox)
5. Click **"Proceed"** button
6. View the **extracted headers** and file information

---

### ⚠️ Troubleshooting

**Problem: "Connection Error"**
- Check internet connection
- Verify SFTP server is accessible: `ftp1.lampsplus.com:9822`

**Problem: "Module not found"**
- Run: `pip install -r requirements.txt`
- Make sure you're in the project directory

**Problem: "Permission denied on keys/lp_key"**
- Mac/Linux users run: `chmod 600 keys/lp_key`

**Problem: Port 5000 already in use**
- Edit `app.py`, change last line:
  ```python
  app.run(debug=True, host='0.0.0.0', port=5001)
  ```

---

### 📁 Project Structure

```
lampsplus-validation/
├── app.py              # Main Flask application
├── requirements.txt    # Dependencies
├── run.sh / run.bat   # Quick start scripts
├── keys/
│   └── lp_key         # SSH private key
├── static/            # CSS and JavaScript files
├── templates/         # HTML templates
└── temp/              # Temporary file storage
```

---

### 🔒 Security Notes

- SSH key (`keys/lp_key`) is used for SFTP authentication
- Session-based authentication with secure cookies
- All credentials are hardcoded for internal use only
- Files are processed in memory and temporarily stored
- Automatic session cleanup on logout

---

### 📞 Support

For issues or questions, contact: **kiran-EA**

---

**Version:** 1.0.0  
**Last Updated:** April 29, 2026
