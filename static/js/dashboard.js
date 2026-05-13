// Dashboard page JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Handle bfcache (back/forward cache)
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) {
            window.location.reload();
        }
    });
    
    // Tab switching
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;
            
            // Remove active class from all tabs
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            // Add active class to clicked tab
            button.classList.add('active');
            document.getElementById(tabName).classList.add('active');
        });
    });
    
    // Mail File Validation functionality
    const loadFilesBtn = document.getElementById('loadFilesBtn');
    const loadFilesText = document.getElementById('loadFilesText');
    const loadFilesLoader = document.getElementById('loadFilesLoader');
    const fileListContainer = document.getElementById('fileListContainer');
    const fileList = document.getElementById('fileList');
    const connectionStatus = document.getElementById('connectionStatus');
    const errorDisplay = document.getElementById('errorDisplay');
    const selectionCount = document.getElementById('selectionCount');
    const proceedBtn = document.getElementById('proceedBtn');
    const proceedText = document.getElementById('proceedText');
    const proceedLoader = document.getElementById('proceedLoader');
    const resultsContainer = document.getElementById('resultsContainer');
    const resultsContent = document.getElementById('resultsContent');
    const clearResultsBtn = document.getElementById('clearResultsBtn');
    
    let selectedFiles = [];
    let selectedFileSizes = {};  // filename -> bytes

    // Load files from SFTP
    loadFilesBtn.addEventListener('click', async function() {
        loadFilesText.textContent = 'Connecting to SFTP...';
        loadFilesLoader.style.display = 'inline-block';
        loadFilesBtn.disabled = true;
        errorDisplay.style.display = 'none';
        fileListContainer.style.display = 'none';

        try {
            const response = await fetch('/api/list-files?path=/FromLP/Catalog Mail Files');
            const data = await response.json();

            if (data.error) {
                errorDisplay.textContent = data.error;
                errorDisplay.style.display = 'block';
                connectionStatus.textContent = 'Connection Failed';
                connectionStatus.classList.remove('connected');
            } else {
                displayFiles(data.files);
                connectionStatus.textContent = 'Connected';
                connectionStatus.classList.add('connected');
                fileListContainer.style.display = 'block';
            }
        } catch (error) {
            errorDisplay.textContent = 'Error connecting to SFTP: ' + error.message;
            errorDisplay.style.display = 'block';
            connectionStatus.textContent = 'Connection Failed';
            connectionStatus.classList.remove('connected');
        } finally {
            loadFilesText.textContent = 'Load Files from SFTP';
            loadFilesLoader.style.display = 'none';
            loadFilesBtn.disabled = false;
        }
    });
    
    // Display files in the list
    function displayFiles(files) {
        fileList.innerHTML = '';
        selectedFiles = [];
        
        if (!files || files.length === 0) {
            fileList.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--gray-600);">No files found</div>';
            return;
        }
        
        files.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = file.name;
            checkbox.dataset.size = file.size || 0;
            checkbox.addEventListener('change', updateSelection);
            
            const fileInfo = document.createElement('div');
            fileInfo.className = 'file-info';
            
            const fileName = document.createElement('div');
            fileName.className = 'file-name';
            fileName.textContent = file.name;
            
            const fileMeta = document.createElement('div');
            fileMeta.className = 'file-meta';
            
            const size = formatBytes(file.size);
            const modified = file.modified;
            
            fileMeta.innerHTML = `
                <span>Size: ${size}</span>
                <span>Modified: ${modified}</span>
            `;
            
            fileInfo.appendChild(fileName);
            fileInfo.appendChild(fileMeta);
            
            fileItem.appendChild(checkbox);
            fileItem.appendChild(fileInfo);
            
            fileList.appendChild(fileItem);
        });
        
        updateSelection();
    }
    
    // Update selection count
    function updateSelection() {
        const checkboxes = fileList.querySelectorAll('input[type="checkbox"]:checked');
        selectedFiles = Array.from(checkboxes).map(cb => cb.value);
        selectedFileSizes = {};
        checkboxes.forEach(cb => { selectedFileSizes[cb.value] = parseInt(cb.dataset.size) || 0; });

        selectionCount.textContent = `${selectedFiles.length} file${selectedFiles.length !== 1 ? 's' : ''} selected`;
        proceedBtn.disabled = selectedFiles.length === 0;
    }

    function estimateSeconds(totalBytes) {
        // ~2 MB/s for SFTP download + processing
        const est = Math.ceil(totalBytes / (2 * 1024 * 1024));
        return Math.max(10, Math.ceil(est / 5) * 5);  // round up to nearest 5, min 10s
    }

    function formatTime(seconds) {
        if (seconds < 60) return `${seconds}s`;
        return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    }
    
    // Process selected files
    proceedBtn.addEventListener('click', async function() {
        if (selectedFiles.length === 0) return;

        proceedText.textContent = 'Processing for Result...';
        proceedLoader.style.display = 'inline-block';
        proceedBtn.disabled = true;

        // Estimated time + elapsed timer
        const totalBytes = Object.values(selectedFileSizes).reduce((a, b) => a + b, 0);
        const estSecs = estimateSeconds(totalBytes);

        let statusBar = document.getElementById('processingStatusBar');
        if (!statusBar) {
            statusBar = document.createElement('div');
            statusBar.id = 'processingStatusBar';
            statusBar.className = 'processing-status-bar';
            proceedBtn.parentNode.insertBefore(statusBar, proceedBtn.nextSibling);
        }

        let elapsed = 0;
        statusBar.innerHTML = `
            <span class="proc-label">Estimated: <strong>~${formatTime(estSecs)}</strong></span>
            <span class="proc-sep">·</span>
            <span class="proc-label">Elapsed: <strong id="elapsedTimer">0s</strong></span>
        `;
        statusBar.style.display = 'flex';

        const timer = setInterval(() => {
            elapsed++;
            const el = document.getElementById('elapsedTimer');
            if (el) el.textContent = formatTime(elapsed);
        }, 1000);

        try {
            const response = await fetch('/api/process-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: selectedFiles, path: '/FromLP/Catalog Mail Files' })
            });

            const data = await response.json();
            displayResults(data.results);
            resultsContainer.style.display = 'block';
            resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });

        } catch (error) {
            alert('Error processing files: ' + error.message);
        } finally {
            clearInterval(timer);
            statusBar.style.display = 'none';
            proceedText.textContent = 'Proceed';
            proceedLoader.style.display = 'none';
            proceedBtn.disabled = false;
        }
    });
    
    // Display processing results
    function displayResults(results) {
        resultsContent.innerHTML = '';
        
        results.forEach(result => {
            if (result.error) {
                const errorCard = document.createElement('div');
                errorCard.className = 'result-card';
                errorCard.innerHTML = `
                    <div class="result-header">
                        <h4>Error</h4>
                    </div>
                    <div class="result-body">
                        <div class="error-display" style="display: block;">
                            ${result.error}
                        </div>
                    </div>
                `;
                resultsContent.appendChild(errorCard);
            } else {
                const card = document.createElement('div');
                card.className = 'result-card';
                
                const header = document.createElement('div');
                header.className = 'result-header';
                header.innerHTML = `<h4>${result.zip_file}</h4>`;
                
                const body = document.createElement('div');
                body.className = 'result-body';
                
                function inlineBadge(pass) {
                    return `<span class="${pass ? 'badge-pass' : 'badge-fail'}" style="font-size:0.7rem;padding:0.1rem 0.45rem;">${pass ? 'PASS' : 'FAIL'}</span>`;
                }

                // Track whether every file in this ZIP passes all rules
                let allCardPass = result.files.length > 0;

                result.files.forEach(file => {
                    const fileResult = document.createElement('div');
                    fileResult.className = 'file-result';

                    const fileHeader = document.createElement('div');
                    fileHeader.className = 'file-result-header';

                    const fileName = document.createElement('div');
                    fileName.className = 'file-result-name';
                    fileName.textContent = file.filename;

                    const status = document.createElement('div');
                    status.className = file.status === 'success' ? 'status-success' : 'status-error';
                    status.textContent = file.status === 'success' ? '✓ Success' : '✗ ' + file.status;

                    fileHeader.appendChild(fileName);
                    fileHeader.appendChild(status);
                    fileResult.appendChild(fileHeader);

                    if (file.status === 'success' && file.header && file.header.length > 0) {
                        const headerDisplay = document.createElement('div');
                        headerDisplay.className = 'header-display';

                        const dataRows   = file.row_count > 0 ? file.row_count - 1 : 0;
                        const rowsPass   = dataRows > 100;
                        const delimPass  = file.delimiter === 'Comma (,)';
                        const custnoVal  = file.custno_null_pct != null ? file.custno_null_pct : null;
                        const keycodeVal = file.keycode_null_pct != null ? file.keycode_null_pct : null;
                        const custnoPass  = custnoVal !== null ? custnoVal <= 5 : true;
                        const keycodePass = keycodeVal !== null ? keycodeVal <= 5 : true;

                        if (!(rowsPass && delimPass && custnoPass && keycodePass)) allCardPass = false;

                        // Column validation badge
                        const colValidation = document.createElement('div');
                        colValidation.className = 'validation-row';
                        const validBadge = document.createElement('span');
                        validBadge.className = file.columns_valid ? 'badge-pass' : 'badge-fail';
                        validBadge.textContent = file.columns_valid ? 'PASS' : 'FAIL';
                        colValidation.innerHTML = '<span class="validation-label">Column Names:</span> ';
                        colValidation.appendChild(validBadge);
                        headerDisplay.appendChild(colValidation);

                        const headerGrid = document.createElement('div');
                        headerGrid.className = 'header-grid';
                        file.header.forEach(col => {
                            const colDiv = document.createElement('div');
                            colDiv.className = 'header-col';
                            colDiv.textContent = col;
                            headerGrid.appendChild(colDiv);
                        });
                        headerDisplay.appendChild(headerGrid);

                        const statsRow = document.createElement('div');
                        statsRow.className = 'stats-row';
                        statsRow.innerHTML = `
                            <span class="stat-item">Total rows: <strong class="${rowsPass ? 'stat-ok' : 'stat-ng'}">${file.row_count}</strong> ${inlineBadge(rowsPass)}</span>
                            <span class="stat-sep">|</span>
                            <span class="stat-item">Delimiter: <strong class="${delimPass ? 'stat-ok' : 'stat-ng'}">${file.delimiter || 'Unknown'}</strong> ${inlineBadge(delimPass)}</span>
                            <span class="stat-sep">|</span>
                            <span class="stat-item">CustNo null: <strong class="${custnoPass ? 'stat-ok' : 'stat-ng'}">${custnoVal !== null ? custnoVal + '%' : 'N/A'}</strong> ${inlineBadge(custnoPass)}</span>
                            <span class="stat-sep">|</span>
                            <span class="stat-item">Keycode null: <strong class="${keycodePass ? 'stat-ok' : 'stat-ng'}">${keycodeVal !== null ? keycodeVal + '%' : 'N/A'}</strong> ${inlineBadge(keycodePass)}</span>
                        `;
                        headerDisplay.appendChild(statsRow);
                        fileResult.appendChild(headerDisplay);
                    } else {
                        allCardPass = false;
                    }

                    body.appendChild(fileResult);
                });

                // Single Load button per ZIP — only if every file passed
                if (allCardPass) {
                    const loadWrap = document.createElement('div');
                    loadWrap.style.padding = '1rem 0 0.25rem';
                    const loadBtn = document.createElement('button');
                    loadBtn.className = 'btn-success mf-load-trigger';
                    loadBtn.style.width = '100%';
                    loadBtn.textContent = 'Load';
                    loadWrap.appendChild(loadBtn);
                    body.appendChild(loadWrap);
                }

                card.appendChild(header);
                card.appendChild(body);

                resultsContent.appendChild(card);
            }
        });
    }

    // Clear results
    clearResultsBtn.addEventListener('click', function() {
        resultsContainer.style.display = 'none';
        resultsContent.innerHTML = '';
    });

    // ==================== Mail File Load Modal ====================
    const mfLoadModal    = document.getElementById('mfLoadModal');
    const mfModalCloseBtn = document.getElementById('mfModalClose');
    const mfRunScriptBtn  = document.getElementById('mfRunScriptBtn');

    resultsContent.addEventListener('click', function (e) {
        const btn = e.target.closest('.mf-load-trigger');
        if (!btn) return;
        mfLoadModal.style.display = 'flex';
        document.getElementById('mfFormSection').style.display = 'block';
        document.getElementById('mfLogSection').style.display = 'none';
    });

    mfModalCloseBtn.addEventListener('click', function () {
        mfLoadModal.style.display = 'none';
    });

    mfLoadModal.addEventListener('click', function (e) {
        if (e.target === mfLoadModal) mfLoadModal.style.display = 'none';
    });

    mfRunScriptBtn.addEventListener('click', async function () {
        const campName = document.getElementById('mfCampName').value.trim();
        if (!campName) { alert('Please enter a Campaign Name.'); return; }

        const res = await fetch('/api/mailfile/start-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camp_name: campName })
        });
        const data = await res.json();
        if (data.error) { alert('Error: ' + data.error); return; }

        document.getElementById('mfFormSection').style.display = 'none';
        const logSection  = document.getElementById('mfLogSection');
        logSection.style.display = 'block';
        const logTerminal = document.getElementById('mfLogTerminal');
        const logStatus   = document.getElementById('mfLogStatus');
        logTerminal.innerHTML = '';
        logStatus.className = 'log-status-running';
        logStatus.textContent = 'Running...';

        const evtSource = new EventSource('/api/mailfile/stream');
        evtSource.onmessage = function (e) {
            const msg = JSON.parse(e.data);
            const line = document.createElement('div');
            line.className = 'log-line';
            line.textContent = msg.line;
            logTerminal.appendChild(line);
            logTerminal.scrollTop = logTerminal.scrollHeight;
            if (msg.done) {
                evtSource.close();
                logStatus.className = 'log-status-done';
                logStatus.textContent = 'Done';
            }
        };
        evtSource.onerror = function () {
            evtSource.close();
            logStatus.className = 'log-status-error';
            logStatus.textContent = 'Connection error';
        };
    });
    
    // Utility function to format bytes
    function formatBytes(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    // ==================== CIRCPLAN TAB ====================

    const cpLoadFilesBtn      = document.getElementById('cpLoadFilesBtn');
    const cpLoadFilesText     = document.getElementById('cpLoadFilesText');
    const cpLoadFilesLoader   = document.getElementById('cpLoadFilesLoader');
    const cpConnectionStatus  = document.getElementById('cpConnectionStatus');
    const cpErrorDisplay      = document.getElementById('cpErrorDisplay');
    const cpFileListContainer = document.getElementById('cpFileListContainer');
    const cpFileList          = document.getElementById('cpFileList');
    const cpSelectionCount    = document.getElementById('cpSelectionCount');
    const cpProceedBtn        = document.getElementById('cpProceedBtn');
    const cpProceedText       = document.getElementById('cpProceedText');
    const cpProceedLoader     = document.getElementById('cpProceedLoader');
    const cpResultsContainer  = document.getElementById('cpResultsContainer');
    const cpResultsContent    = document.getElementById('cpResultsContent');
    const cpClearResultsBtn   = document.getElementById('cpClearResultsBtn');

    let cpSelectedFiles = [];
    let cpSelectedSizes = {};

    cpLoadFilesBtn.addEventListener('click', async function () {
        cpLoadFilesText.textContent = 'Connecting to SFTP...';
        cpLoadFilesLoader.style.display = 'inline-block';
        cpLoadFilesBtn.disabled = true;
        cpErrorDisplay.style.display = 'none';
        cpFileListContainer.style.display = 'none';

        try {
            const response = await fetch('/api/circplan/list-files');
            const data = await response.json();

            if (data.error) {
                cpErrorDisplay.textContent = data.error;
                cpErrorDisplay.style.display = 'block';
                cpConnectionStatus.textContent = 'Connection Failed';
                cpConnectionStatus.classList.remove('connected');
            } else {
                cpDisplayFiles(data.files);
                cpConnectionStatus.textContent = 'Connected';
                cpConnectionStatus.classList.add('connected');
                cpFileListContainer.style.display = 'block';
            }
        } catch (err) {
            cpErrorDisplay.textContent = 'Error: ' + err.message;
            cpErrorDisplay.style.display = 'block';
            cpConnectionStatus.textContent = 'Connection Failed';
            cpConnectionStatus.classList.remove('connected');
        } finally {
            cpLoadFilesText.textContent = 'Load Files from SFTP';
            cpLoadFilesLoader.style.display = 'none';
            cpLoadFilesBtn.disabled = false;
        }
    });

    function cpDisplayFiles(files) {
        cpFileList.innerHTML = '';
        cpSelectedFiles = [];
        if (!files || files.length === 0) {
            cpFileList.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--gray-600);">No files found</div>';
            return;
        }
        files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'file-item';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.value = file.name;
            cb.dataset.size = file.size || 0;
            cb.addEventListener('change', cpUpdateSelection);

            const info = document.createElement('div');
            info.className = 'file-info';

            const name = document.createElement('div');
            name.className = 'file-name';
            name.textContent = file.name;

            const meta = document.createElement('div');
            meta.className = 'file-meta';
            meta.innerHTML = `<span>Size: ${formatBytes(file.size)}</span><span>Modified: ${file.modified}</span>`;

            info.appendChild(name);
            info.appendChild(meta);
            item.appendChild(cb);
            item.appendChild(info);
            cpFileList.appendChild(item);
        });
        cpUpdateSelection();
    }

    function cpUpdateSelection() {
        const checked = cpFileList.querySelectorAll('input[type="checkbox"]:checked');
        cpSelectedFiles = Array.from(checked).map(cb => cb.value);
        cpSelectedSizes = {};
        checked.forEach(cb => { cpSelectedSizes[cb.value] = parseInt(cb.dataset.size) || 0; });
        cpSelectionCount.textContent = `${cpSelectedFiles.length} file${cpSelectedFiles.length !== 1 ? 's' : ''} selected`;
        cpProceedBtn.disabled = cpSelectedFiles.length === 0;
    }

    cpProceedBtn.addEventListener('click', async function () {
        if (cpSelectedFiles.length === 0) return;

        cpProceedText.textContent = 'Processing for Result...';
        cpProceedLoader.style.display = 'inline-block';
        cpProceedBtn.disabled = true;

        const totalBytes = Object.values(cpSelectedSizes).reduce((a, b) => a + b, 0);
        const estSecs = estimateSeconds(totalBytes);
        let cpStatusBar = document.getElementById('cpProcessingStatusBar');
        if (!cpStatusBar) {
            cpStatusBar = document.createElement('div');
            cpStatusBar.id = 'cpProcessingStatusBar';
            cpStatusBar.className = 'processing-status-bar';
            cpProceedBtn.parentNode.insertBefore(cpStatusBar, cpProceedBtn.nextSibling);
        }
        let elapsed = 0;
        cpStatusBar.innerHTML = `
            <span class="proc-label">Estimated: <strong>~${formatTime(estSecs)}</strong></span>
            <span class="proc-sep">·</span>
            <span class="proc-label">Elapsed: <strong id="cpElapsedTimer">0s</strong></span>`;
        cpStatusBar.style.display = 'flex';
        const timer = setInterval(() => {
            elapsed++;
            const el = document.getElementById('cpElapsedTimer');
            if (el) el.textContent = formatTime(elapsed);
        }, 1000);

        try {
            const response = await fetch('/api/circplan/process-files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: cpSelectedFiles })
            });
            const data = await response.json();
            cpDisplayResults(data.results);
            cpResultsContainer.style.display = 'block';
            cpResultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (err) {
            alert('Error: ' + err.message);
        } finally {
            clearInterval(timer);
            cpStatusBar.style.display = 'none';
            cpProceedText.textContent = 'Proceed';
            cpProceedLoader.style.display = 'none';
            cpProceedBtn.disabled = false;
        }
    });

    function cpDisplayResults(results) {
        cpResultsContent.innerHTML = '';
        results.forEach(result => {
            if (result.error) {
                const card = document.createElement('div');
                card.className = 'result-card';
                card.innerHTML = `<div class="result-header"><h4>Error</h4></div>
                    <div class="result-body"><div class="error-display" style="display:block;">${result.error}</div></div>`;
                cpResultsContent.appendChild(card);
                return;
            }

            const card = document.createElement('div');
            card.className = 'result-card';
            card.innerHTML = `<div class="result-header"><h4>${result.zip_file}</h4></div>`;

            const body = document.createElement('div');
            body.className = 'result-body';

            result.files.forEach(file => {
                const fileResult = document.createElement('div');
                fileResult.className = 'file-result';

                const fileHeader = document.createElement('div');
                fileHeader.className = 'file-result-header';
                fileHeader.innerHTML = `
                    <div class="file-result-name">${file.filename}</div>
                    <div class="${file.status === 'success' ? 'status-success' : 'status-error'}">
                        ${file.status === 'success' ? '✓ Success' : '✗ ' + file.status}
                    </div>`;
                fileResult.appendChild(fileHeader);

                if (file.status === 'success' && file.header && file.header.length > 0) {
                    const headerDisplay = document.createElement('div');
                    headerDisplay.className = 'header-display';

                    // QC checks
                    const delimPass  = (file.delimiter || '').indexOf('Pipe') !== -1;
                    const colsPass   = file.columns_valid === true;
                    const keyCodeVal = (file.keycode_null_pct !== null && file.keycode_null_pct !== undefined) ? file.keycode_null_pct : null;
                    const keyPass    = keyCodeVal !== null ? keyCodeVal <= 5 : true;
                    const allPass    = delimPass && colsPass && keyPass;

                    function rIcon(pass) {
                        return `<span class="rule-icon ${pass ? 'rule-pass' : 'rule-fail'}">${pass ? '✓' : '✗'}</span>`;
                    }

                    const ruleBox = document.createElement('div');
                    ruleBox.className = `rule-box ${allPass ? 'rule-box-pass' : 'rule-box-fail'}`;
                    ruleBox.innerHTML = `
                        <div class="rule-title">
                            QC Validation
                            <span class="${allPass ? 'badge-pass' : 'badge-fail'}">${allPass ? 'ALL PASS' : 'FAILED'}</span>
                        </div>
                        <div class="rule-list">
                            <div class="rule-row">
                                ${rIcon(delimPass)}
                                <span class="rule-label">Delimiter is Pipe (|)</span>
                                <span class="${delimPass ? 'rule-detail' : 'rule-detail-fail'}">${file.delimiter || 'Unknown'}</span>
                            </div>
                            <div class="rule-row">
                                ${rIcon(colsPass)}
                                <span class="rule-label">Column names match</span>
                                <span class="${colsPass ? 'rule-detail' : 'rule-detail-fail'}">${colsPass ? 'Exact match' : 'Mismatch'}</span>
                            </div>
                            <div class="rule-row">
                                ${rIcon(keyPass)}
                                <span class="rule-label">Key Code null ≤ 5%</span>
                                <span class="${keyPass ? 'rule-detail' : 'rule-detail-fail'}">${keyCodeVal !== null ? keyCodeVal + '%' : 'N/A'}</span>
                            </div>
                        </div>`;
                    headerDisplay.appendChild(ruleBox);

                    // Header columns grid
                    const grid = document.createElement('div');
                    grid.className = 'header-grid';
                    file.header.forEach(col => {
                        const colDiv = document.createElement('div');
                        colDiv.className = 'header-col';
                        colDiv.textContent = col;
                        grid.appendChild(colDiv);
                    });
                    headerDisplay.appendChild(grid);

                    // Stats row
                    const stats = document.createElement('div');
                    stats.className = 'stats-row';
                    stats.innerHTML = `
                        <span class="stat-item">Total rows: <strong>${file.row_count}</strong></span>
                        <span class="stat-sep">|</span>
                        <span class="stat-item">Delimiter: <strong class="${delimPass ? 'stat-ok' : 'stat-ng'}">${file.delimiter || 'Unknown'}</strong></span>
                        <span class="stat-sep">|</span>
                        <span class="stat-item">Key Code null: <strong class="${keyPass ? 'stat-ok' : 'stat-ng'}">${keyCodeVal !== null ? keyCodeVal + '%' : 'N/A'}</strong> <span class="${keyPass ? 'badge-pass' : 'badge-fail'}" style="font-size:0.7rem;padding:0.1rem 0.45rem;">${keyPass ? 'PASS' : 'FAIL'}</span></span>`;
                    headerDisplay.appendChild(stats);

                    // Load button — only if all QC rules pass
                    if (allPass) {
                        const loadWrap = document.createElement('div');
                        loadWrap.style.marginTop = '1rem';
                        const loadBtn = document.createElement('button');
                        loadBtn.className = 'btn-success cp-load-trigger';
                        loadBtn.dataset.filename = file.filename;
                        loadBtn.style.width = '100%';
                        loadBtn.textContent = 'Load';
                        loadWrap.appendChild(loadBtn);
                        headerDisplay.appendChild(loadWrap);
                    }

                    fileResult.appendChild(headerDisplay);
                }
                body.appendChild(fileResult);
            });

            card.appendChild(body);
            cpResultsContent.appendChild(card);
        });
    }

    cpClearResultsBtn.addEventListener('click', function () {
        cpResultsContainer.style.display = 'none';
        cpResultsContent.innerHTML = '';
    });

    // ==================== CircPlan Load Modal ====================
    const cpLoadModal    = document.getElementById('cpLoadModal');
    const cpModalCloseBtn = document.getElementById('cpModalClose');
    const cpZipTypeSelect = document.getElementById('cpZipType');
    const cpRunScriptBtn  = document.getElementById('cpRunScriptBtn');

    // Delegate Load button clicks from results
    cpResultsContent.addEventListener('click', function (e) {
        const btn = e.target.closest('.cp-load-trigger');
        if (!btn) return;
        cpLoadModal.style.display = 'flex';
        document.getElementById('cpFormSection').style.display = 'block';
        document.getElementById('cpLogSection').style.display = 'none';
    });

    cpModalCloseBtn.addEventListener('click', function () {
        cpLoadModal.style.display = 'none';
    });

    cpLoadModal.addEventListener('click', function (e) {
        if (e.target === cpLoadModal) cpLoadModal.style.display = 'none';
    });

    cpZipTypeSelect.addEventListener('change', function () {
        if (cpZipTypeSelect.value === 'combined') {
            document.getElementById('cpMailFileSingleGroup').style.display = 'block';
            document.getElementById('cpMailFileMultiGroup').style.display = 'none';
        } else {
            document.getElementById('cpMailFileSingleGroup').style.display = 'none';
            document.getElementById('cpMailFileMultiGroup').style.display = 'block';
        }
    });

    cpRunScriptBtn.addEventListener('click', async function () {
        const campName    = document.getElementById('cpCampName').value.trim();
        const isNtf       = document.getElementById('cpIsNtf').value;
        const keycodeFile = document.getElementById('cpKeycodeFile').value.trim();
        const zipType     = cpZipTypeSelect.value;
        const mailFile    = document.getElementById('cpMailFile').value.trim();
        const mailFiles   = document.getElementById('cpMailFiles').value.trim();

        if (!campName || !keycodeFile) {
            alert('Please fill in Campaign Name and Keycode File Name.');
            return;
        }
        const mailFileValue = zipType === 'combined' ? mailFile : mailFiles;
        if (!mailFileValue) {
            alert('Please fill in the mail file name(s).');
            return;
        }

        const res = await fetch('/api/circplan/start-script', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ camp_name: campName, is_ntf: isNtf, keycode_file: keycodeFile, zip_type: zipType, mail_file: mailFileValue })
        });
        const data = await res.json();
        if (data.error) { alert('Error: ' + data.error); return; }

        document.getElementById('cpFormSection').style.display = 'none';
        const logSection  = document.getElementById('cpLogSection');
        logSection.style.display = 'block';
        const logTerminal = document.getElementById('cpLogTerminal');
        const logStatus   = document.getElementById('cpLogStatus');
        logTerminal.innerHTML = '';
        logStatus.className = 'log-status-running';
        logStatus.textContent = 'Running...';

        const evtSource = new EventSource('/api/circplan/stream');
        evtSource.onmessage = function (e) {
            const msg = JSON.parse(e.data);
            const line = document.createElement('div');
            line.className = 'log-line';
            line.textContent = msg.line;
            logTerminal.appendChild(line);
            logTerminal.scrollTop = logTerminal.scrollHeight;
            if (msg.done) {
                evtSource.close();
                logStatus.className = 'log-status-done';
                logStatus.textContent = 'Done';
            }
        };
        evtSource.onerror = function () {
            evtSource.close();
            logStatus.className = 'log-status-error';
            logStatus.textContent = 'Connection error';
        };
    });
});
