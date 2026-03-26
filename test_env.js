const document = {getElementById: (id) => ({value: "", disabled: false, style: {}, classList: {add: ()=>{}, remove: ()=>{}}, innerHTML: "", getContext: ()=>({})}), addEventListener: ()=>{}, querySelectorAll: ()=>[]};
const window = {}; 
const fetch = async () => ({json: async () => ({})}); 
const localStorage = {getItem: ()=>{}, setItem: ()=>{}, removeItem: ()=>{}};

    /* ── State ─────────────────────────────────────────────── */
    let selPredVideo = null, selFullVideo = null, selFullAudio = null;

    /* ── Login / Navigation ────────────────────────────────── */
    function goToDashboard() {
        document.getElementById('homePage').style.display = 'none';
        document.getElementById('dashboardPage').style.display = 'block';
        initDashboard();
    }

    function goToHome() {
        document.getElementById('dashboardPage').style.display = 'none';
        document.getElementById('homePage').style.display = 'flex';
    }

    function openToolFromHome(toolId, btnIndex) {
        goToDashboard();
        const btns = document.querySelectorAll('.nav-item');
        navigate(btns[btnIndex] || null, toolId);
    }

    function handleLogin(e) {
        e.preventDefault();
        const email = document.getElementById('loginEmail').value;
        const pass  = document.getElementById('loginPassword').value;
        const btn   = document.getElementById('loginBtn');
        const err   = document.getElementById('loginError');

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Signing in…';

        fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: pass })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                localStorage.setItem('currentUser', JSON.stringify({ id: data.user_id, email: data.email }));
                document.getElementById('loginPage').style.display = 'none';
                document.getElementById('homePage').style.display = 'flex';
            } else {
                document.getElementById('loginErrorMsg').textContent = data.error || 'Invalid email or password';
                err.classList.add('show');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign In';
                setTimeout(() => err.classList.remove('show'), 3000);
            }
        })
        .catch(() => {
            document.getElementById('loginErrorMsg').textContent = 'Server error. Please try again.';
            err.classList.add('show');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign In';
            setTimeout(() => err.classList.remove('show'), 3000);
        });
    }

    function handleRegister(e) {
        e.preventDefault();
        const email   = document.getElementById('regEmail').value;
        const pass    = document.getElementById('regPassword').value;
        const confirm = document.getElementById('regConfirm').value;
        const btn     = document.getElementById('registerBtn');
        const err     = document.getElementById('registerError');
        const success = document.getElementById('registerSuccess');

        if (pass !== confirm) {
            document.getElementById('registerErrorMsg').textContent = 'Passwords do not match';
            err.classList.add('show');
            setTimeout(() => err.classList.remove('show'), 3000);
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registering…';

        fetch('/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: pass })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                success.classList.add('show');
                setTimeout(() => {
                    success.classList.remove('show');
                    showLoginPage();
                }, 2000);
            } else {
                document.getElementById('registerErrorMsg').textContent = data.error || 'Registration failed';
                err.classList.add('show');
                setTimeout(() => err.classList.remove('show'), 3000);
            }
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-user-plus"></i> Register';
        })
        .catch(() => {
            document.getElementById('registerErrorMsg').textContent = 'Server error. Please try again.';
            err.classList.add('show');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-user-plus"></i> Register';
            setTimeout(() => err.classList.remove('show'), 3000);
        });
    }

    function showRegisterPage() {
        document.getElementById('loginPage').style.display = 'none';
        document.getElementById('registerPage').style.display = 'flex';
        document.getElementById('registerForm').reset();
    }

    function showLoginPage() {
        document.getElementById('registerPage').style.display = 'none';
        document.getElementById('loginPage').style.display = 'flex';
        document.getElementById('loginForm').reset();
    }

    function logout() {
        localStorage.removeItem('currentUser');
        document.getElementById('loginPage').style.display = 'flex';
        document.getElementById('registerPage').style.display = 'none';
        document.getElementById('homePage').style.display = 'none';
        document.getElementById('dashboardPage').style.display = 'none';
        
        // Hide admin page if it exists
        const adminDash = document.getElementById('adminDashboardPage');
        if(adminDash) adminDash.style.display = 'none';

        document.getElementById('loginForm').reset();
        document.getElementById('adminLoginForm').reset();
        document.getElementById('adminRegisterForm').reset();
        document.getElementById('loginBtn').disabled = false;
        document.getElementById('loginBtn').innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign In';
        selPredVideo = selFullVideo = selFullAudio = null;
    }

    /* ── Admin Auth Handlers ──────────────────────────────── */
    function toggleAdminLogin() {
        const sec = document.getElementById('adminLoginSection');
        sec.style.display = sec.style.display === 'none' ? 'block' : 'none';
    }

    function toggleAdminRegister() {
        const frm = document.getElementById('adminRegisterForm');
        frm.style.display = frm.style.display === 'none' ? 'block' : 'none';
    }

    function handleAdminLogin(e) {
        e.preventDefault();
        const email = document.getElementById('adminEmail').value;
        const pass  = document.getElementById('adminPassword').value;
        const btn   = document.getElementById('adminLoginBtn');
        const err   = document.getElementById('adminLoginError');

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking…';

        fetch('/admin/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: pass })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                localStorage.setItem('currentUser', JSON.stringify({ id: data.admin_id, email: data.email, role: 'admin' }));
                document.getElementById('loginPage').style.display = 'none';
                
                // Route to Admin Dashboard Page (created in Phase 4)
                const adp = document.getElementById('adminDashboardPage');
                if (adp) {
                    adp.style.display = 'block';
                    loadAdminDashboard();
                } else {
                    document.getElementById('homePage').style.display = 'flex'; // fallback
                }
            } else {
                document.getElementById('adminLoginErrorMsg').textContent = data.error || 'Invalid credentials';
                err.classList.add('show');
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-shield-alt"></i> Admin Sign In';
                setTimeout(() => err.classList.remove('show'), 3000);
            }
        }).catch(() => {
            document.getElementById('adminLoginErrorMsg').textContent = 'Server error. Please try again.';
            err.classList.add('show');
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-shield-alt"></i> Admin Sign In';
            setTimeout(() => err.classList.remove('show'), 3000);
        });
    }

    function handleAdminRegister(e) {
        e.preventDefault();
        const email = document.getElementById('adminRegEmail').value;
        const pass  = document.getElementById('adminRegPassword').value;
        const btn   = document.getElementById('adminRegisterBtn');

        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing…';

        fetch('/admin/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password: pass })
        }).then(r => r.json()).then(data => {
            if (data.success) {
                alert("Internal Admin Node Initialized Successfully. Please Sign In.");
                document.getElementById('adminRegisterForm').style.display = 'none';
                document.getElementById('adminRegisterForm').reset();
            } else {
                alert(data.error || "Initialization failed.");
            }
            btn.disabled = false;
            btn.innerHTML = 'Initialize Admin';
        }).catch(() => {
            alert("Network error.");
            btn.disabled = false;
            btn.innerHTML = 'Initialize Admin';
        });
    }

    /* ── Init ──────────────────────────────────────────────── */
    let _dashboardReady = false;
    function initDashboard() {
        if (_dashboardReady) return;   // only attach listeners ONCE
        _dashboardReady = true;
        setupDrop('predVideoArea',  'predVideoInput',  f => handleVideo(f, 'pred'));
        setupDrop('fullVideoArea',  'fullVideoInput',  f => handleVideo(f, 'full'));
        setupDrop('fullAudioArea',  'fullAudioInput',  f => handleAudio(f, 'full'));
    }

    /* ── Sidebar / Nav ─────────────────────────────────────── */
    function toggleSidebar() {
        document.getElementById('sidebar').classList.toggle('open');
    }

    function navigate(el, id) {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        if (el) el.classList.add('active');
        ['prediction-only-card','full-pipeline-card','history-card'].forEach(c => {
            const card = document.getElementById(c);
            if(card) card.style.display = 'none';
        });
        const target = document.getElementById(id + '-card');
        if (target) { target.style.display = 'block'; target.scrollIntoView({ behavior:'smooth', block:'start' }); }

        if (id === 'history') {
            loadHistory();
        }
    }

    function showHelp() {
        showToast('Select a mode from the sidebar, upload required files, then click the action button to process.');
    }

    function showToast(msg) {
        const t = document.createElement('div');
        t.className = 'toast';
        t.innerHTML = `<i class="fas fa-info-circle"></i><span>${msg}</span>`;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 5000);
    }

    /* ── Drag & Drop ───────────────────────────────────────── */
    function setupDrop(areaId, inputId, handler) {
        const area  = document.getElementById(areaId);
        const input = document.getElementById(inputId);
        if (!area || !input) return;

        area.addEventListener('dragover',  e => { e.preventDefault(); area.classList.add('dragover'); });
        area.addEventListener('dragleave', () => area.classList.remove('dragover'));
        area.addEventListener('drop', e => {
            e.preventDefault();
            area.classList.remove('dragover');
            if (e.dataTransfer.files[0]) handler(e.dataTransfer.files[0]);
        });
        /* only trigger file picker when clicking the area itself, not child buttons */
        area.addEventListener('click', e => {
            if (e.target.tagName !== 'BUTTON' && !e.target.closest('button')) {
                input.click();
            }
        });
        /* prevent nested upload-btn from also bubbling to area */
        area.querySelectorAll('.upload-btn').forEach(btn => {
            btn.addEventListener('click', e => { e.stopPropagation(); input.click(); });
        });
        input.addEventListener('change', e => { if (e.target.files[0]) handler(e.target.files[0]); });
    }

    /* ── File handlers ─────────────────────────────────────── */
    function handleVideo(file, mode) {
        const resultId = mode === 'pred' ? 'predResult' : 'fullResult';
        if (!/\.(mp4|avi|mov|mkv|webm)$/i.test(file.name)) {
            return showResultError(resultId, 'Invalid video type. Use MP4, AVI, MOV, MKV or WebM.');
        }
        if (file.size > 200 * 1024 * 1024) {
            return showResultError(resultId, 'Video must be under 200 MB.');
        }
        clearResult(resultId);
        if (mode === 'pred') {
            selPredVideo = file;
            updateFileInfo('predFileInfo', [{icon:'fa-film', label:'Video', file}]);
            document.getElementById('predBtn').disabled = false;
            document.getElementById('predVideoArea').classList.add('has-file');
        } else {
            selFullVideo = file;
            refreshFullInfo();
            updateFullBtn();
            document.getElementById('fullVideoArea').classList.add('has-file');
        }
    }

    function handleAudio(file, mode) {
        if (!/\.(wav|mp3|m4a|flac)$/i.test(file.name)) {
            const resultId = mode === 'full' ? 'fullResult' : null;
            if (resultId) showResultError(resultId, 'Invalid audio type. Use WAV, MP3, M4A or FLAC.');
            return;
        }
        if (mode === 'full') {
            selFullAudio = file;
            refreshFullInfo();
            updateFullBtn();
            document.getElementById('fullAudioArea').classList.add('has-file');
        }
    }

    function updateFileInfo(elId, items) {
        const el = document.getElementById(elId);
        if (!el) return;
        el.innerHTML = items.map(({icon,label,file}) =>
            `<span class="file-info-item"><i class="fas ${icon}"></i><strong>${label}:</strong> ${file.name} <span style="color:var(--text-3)">(${(file.size/1024/1024).toFixed(2)} MB)</span></span>`
        ).join('');
        el.classList.add('show');
    }

    function refreshFullInfo() {
        const items = [];
        if (selFullVideo) items.push({icon:'fa-film',       label:'Video', file:selFullVideo});
        if (selFullAudio) items.push({icon:'fa-microphone', label:'Audio', file:selFullAudio});
        if (items.length) updateFileInfo('fullFileInfo', items);
    }

    function updateFullBtn() {
        document.getElementById('fullBtn').disabled = !(selFullVideo && selFullAudio);
    }

    /* ── Mock data (used when backend unreachable) ─────────── */
    const MOCK_SENTENCES = [
        'Place place it in my hand',
        'Bin blue at F two now',
        'Lay red by A nine please',
        'Set white with G six soon',
        'Place green at C four again',
    ];

    function mockData(mode) {
        const picked = MOCK_SENTENCES[Math.floor(Math.random() * MOCK_SENTENCES.length)];
        const conf   = 0.72 + Math.random() * 0.25;
        const probs  = {};
        MOCK_SENTENCES.forEach(s => { probs[s] = s === picked ? conf : Math.random() * 0.18; });
        return {
            predicted_sentence: picked,
            confidence: conf,
            all_probs: probs,
            /* prediction mode: no generated outputs, just the uploaded video preview
               full pipeline:   cloned audio + output video from backend            */
            audio_path: mode === 'full' ? 'outputs/cloned_voice.wav'    : null,
            video_path: mode === 'full' ? 'outputs/output_with_voice.mp4' : null,
        };
    }

    /* ── API calls ─────────────────────────────────────────── */
    async function processPrediction() {
        if (!selPredVideo) return;
        await runRequest('predLoading', 'predBtn', 'predResult', 'prediction');
    }

    async function processFullPipeline() {
        if (!selFullVideo || !selFullAudio) return;
        await runRequest('fullLoading', 'fullBtn', 'fullResult', 'full');
    }

    async function runRequest(loadingId, btnId, resultId, mode) {
        const loading = document.getElementById(loadingId);
        const btn     = document.getElementById(btnId);

        /* reset result panel */
        clearResult(resultId);
        loading.classList.add('show');
        document.getElementById(loadingId + 'Text').innerHTML = `<i class="fas fa-spinner fa-spin"></i> Initializing...`;
        
        const pContainer = document.getElementById(loadingId.replace('Loading', 'ProgressContainer'));
        const pBar = document.getElementById(loadingId.replace('Loading', 'ProgressBar'));
        if (pContainer && pBar) {
            pContainer.style.display = 'block';
            pBar.style.width = '5%';
        }
        
        btn.disabled = true;

        const currentUserObj = localStorage.getItem('currentUser');
        const currentUser = currentUserObj ? JSON.parse(currentUserObj) : null;

        try {
            const fd = new FormData();
            if (mode === 'prediction') {
                fd.append('video', selPredVideo);
                fd.append('mode', 'prediction');
            } else {
                fd.append('video', selFullVideo);
                fd.append('audio', selFullAudio);
                fd.append('mode', 'full');
            }
            if (currentUser) fd.append('user_id', currentUser.id);

            const res = await fetch('/process', { method: 'POST', body: fd });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            
            if (data.error) {
                showResultError(resultId, data.error);
                loading.classList.remove('show');
                btn.disabled = false;
                return;
            }

            let progressInterval = null;
            let currentPct = 5;

            // Setup SSE Stream for Live Progress
            const evtSource = new EventSource('/stream/' + data.task_id);
            evtSource.onmessage = function(event) {
                const taskData = JSON.parse(event.data);
                
                if (taskData.error) {
                    if(progressInterval) clearInterval(progressInterval);
                    showResultError(resultId, taskData.error);
                    loading.classList.remove('show');
                    btn.disabled = false;
                    evtSource.close();
                } else if (taskData.status === 'complete') {
                    if(progressInterval) clearInterval(progressInterval);
                    currentPct = 100;
                    if (pBar) pBar.style.width = '100%';
                    document.getElementById(loadingId + 'Text').innerHTML = `<i class="fas fa-check-circle" style="color:#10b981;"></i> Complete (100%)`;
                    
                    setTimeout(() => {
                        showResultSuccess(resultId, taskData.result, mode);
                        loading.classList.remove('show');
                        btn.disabled = false;
                    }, 600);
                    evtSource.close();
                } else if (taskData.status === 'running') {
                    // Determine where the bar "should" be based on the current step
                    let targetPct = mode === 'prediction' ? 95 : 15;
                    if (mode === 'full') {
                        if (taskData.progress_msg.includes('Step 1')) targetPct = 35;
                        if (taskData.progress_msg.includes('Step 2')) targetPct = 75;
                        if (taskData.progress_msg.includes('Generating')) targetPct = 85;
                        if (taskData.progress_msg.includes('Step 3')) targetPct = 95;
                    }
                    
                    // Start smooth animation interval if not started
                    if (!progressInterval) {
                        progressInterval = setInterval(() => {
                            if (currentPct < targetPct) {
                                // Crawl upwards. Crawls slower as it gets closer to the target.
                                currentPct += Math.max(0.1, (targetPct - currentPct) * 0.05);
                                if (currentPct > targetPct - 0.5) currentPct = targetPct;
                                
                                if (pBar) pBar.style.width = currentPct + '%';
                                
                                // Update live progress text with the climbed percentage
                                const textEl = document.getElementById(loadingId + 'Text');
                                if (textEl) {
                                    textEl.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${taskData.progress_msg} <strong style="color:var(--accent); margin-left:8px;">${Math.floor(currentPct)}%</strong>`;
                                }
                            }
                        }, 250);
                    }
                }
            };
            
            evtSource.onerror = function(err) {
                if(progressInterval) clearInterval(progressInterval);
                console.warn('SSE Error:', err);
                evtSource.close();
                showResultError(resultId, 'Lost connection to backend process.');
                loading.classList.remove('show');
                btn.disabled = false;
            };

        } catch (err) {
            console.warn('Backend unreachable or error:', err.message);
            showResultError(resultId, 'Process failed: ' + err.message);
            loading.classList.remove('show');
            btn.disabled = false;
        }
    }

    /* ── History (My Projects) ─────────────────────────────── */
    async function loadHistory() {
        const currentUserObj = localStorage.getItem('currentUser');
        if (!currentUserObj) return;

        const user = JSON.parse(currentUserObj);
        const grid = document.getElementById('historyGrid');
        const loading = document.getElementById('historyLoading');

        grid.innerHTML = '';
        loading.style.display = 'block';

        try {
            const res = await fetch('/api/projects/' + user.id);
            if (!res.ok) throw new Error('Failed to load history');
            const projects = await res.json();
            
            loading.style.display = 'none';

            if (projects.length === 0) {
                grid.innerHTML = '<div style="text-align:center; padding:3rem; color:var(--text-3); background:rgba(0,0,0,0.2); border-radius:12px;">No projects generated yet.</div>';
                return;
            }

            grid.innerHTML = projects.map(p => `
                <div class="card" style="background: rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.1); padding:1.5rem;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem; border-bottom:1px solid rgba(255,255,255,0.05); padding-bottom:1rem;">
                        <span class="badge ${p.type === 'full' ? 'badge-full' : 'badge-pred'}">
                            ${p.type === 'full' ? '<i class="fas fa-magic"></i> Full Pipeline' : '<i class="fas fa-eye"></i> Prediction Only'}
                        </span>
                        <span style="font-size:0.875rem; color:var(--text-3);"><i class="far fa-clock"></i> ${new Date(p.created_at + 'Z').toLocaleString()}</span>
                    </div>
                    
                    <div style="margin-bottom:1.5rem;">
                        <h4 style="font-size:0.875rem; color:var(--text-3); text-transform:uppercase; letter-spacing:1px; margin-bottom:0.5rem;">Predicted Text</h4>
                        <div style="font-size:1.1rem; font-weight:500; color:var(--text); padding:1rem; background:rgba(0,0,0,0.3); border-radius:8px; border-left:4px solid var(--accent);">
                            "${p.predicted_sentence || 'No prediction available'}"
                        </div>
                    </div>

                    ${p.video_file || p.audio_file ? `
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:1rem;">
                        ${p.video_file ? `
                            <div>
                                <h4 style="font-size:0.875rem; color:var(--text-3); margin-bottom:0.5rem;">Generated Video</h4>
                                <a href="/download/video/${p.video_file}" class="action-btn" style="padding:0.6rem; font-size:0.9rem;" download>
                                    <i class="fas fa-video"></i> Download Video
                                </a>
                            </div>
                        ` : ''}
                        ${p.audio_file ? `
                            <div>
                                <h4 style="font-size:0.875rem; color:var(--text-3); margin-bottom:0.5rem;">Cloned Audio</h4>
                                <a href="/download/audio/${p.audio_file}" class="action-btn" style="padding:0.6rem; font-size:0.9rem; background:rgba(255,255,255,0.1);" download>
                                    <i class="fas fa-music"></i> Download Audio
                                </a>
                            </div>
                        ` : ''}
                    </div>
                    ` : ''}
                </div>
            `).join('');
            
        } catch(err) {
            loading.style.display = 'none';
            grid.innerHTML = `<div class="result-panel error" style="display:block;">Failed to load project history.</div>`;
            console.error(err);
        }
    }

    /* ── Admin Dashboard Population ────────────────────────── */
    async function loadAdminDashboard() {
        try {
            // 1. Fetch Stats
            const statsRes = await fetch('/api/admin/stats');
            const stats = await statsRes.json();
            document.getElementById('adminStatVideos').innerText = stats.total_projects;
            document.getElementById('adminStatClones').innerText = stats.total_clones;
            document.getElementById('adminStatUsers').innerText = stats.total_users;
            document.getElementById('adminStatFeedback').innerText = stats.total_feedback;

            // 1.5 Render grouped bar chart
            const fbStatsRes = await fetch('/api/admin/feedback-stats');
            const fbStats = await fbStatsRes.json();
            renderFeedbackBarChart(fbStats);

            // 2. Fetch Projects / Predictions
            const projRes = await fetch('/api/admin/projects');
            const projs = await projRes.json();
            const pTable = document.getElementById('adminProjectsTable');
            if (projs.length === 0) {
                pTable.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:2rem; color:var(--text-3);">No system activity yet.</td></tr>`;
            } else {
                pTable.innerHTML = projs.map(p => `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:1rem 1.5rem; color:var(--text-2); font-size:0.85rem;">${new Date(p.created_at + 'Z').toLocaleString()}</td>
                        <td style="padding:1rem 1.5rem; color:var(--primary); font-family:monospace;">${p.user_email || 'Unknown User'}</td>
                        <td style="padding:1rem 1.5rem;">
                            <span class="badge ${p.type === 'full' ? 'badge-full' : 'badge-pred'}" style="font-size:0.75rem; padding:0.25rem 0.6rem;">${p.type.toUpperCase()}</span>
                        </td>
                        <td style="padding:1rem 1.5rem; font-weight:500;">"${p.predicted_sentence || '...'}"</td>
                    </tr>
                `).join('');
            }

            // 3. Fetch Feedback
            const fbRes = await fetch('/api/admin/feedback');
            const fb = await fbRes.json();
            const fList = document.getElementById('adminFeedbackList');
            if (fb.length === 0) {
                fList.innerHTML = `<div style="text-align:center; padding:2rem; color:var(--text-3); background:rgba(0,0,0,0.2); border-radius:8px;">No user feedback submitted yet.</div>`;
            } else {
                fList.innerHTML = fb.map(f => {
                    const moduleLabels = {
                        'video_cloning': 'Video Cloning',
                        'audio_cloning': 'Audio Cloning',
                        'sentence_prediction': 'Sentence Prediction'
                    };
                    const moduleLabel = moduleLabels[f.module_type] || f.module_type || 'Unknown';
                    return `
                    <div style="background:rgba(255,255,255,0.03); border-left:3px solid ${f.satisfied ? '#10b981' : '#ef4444'}; padding:1.25rem; border-radius:4px; margin-bottom:1rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem; flex-wrap:wrap; gap:0.5rem;">
                            <strong style="color:var(--text-1);"><i class="fas fa-user-circle"></i> ${f.user_email}</strong>
                            <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                                <span style="background:rgba(59,130,246,0.1); color:#93c5fd; border:1px solid rgba(59,130,246,0.2); font-size:0.65rem; padding:0.15rem 0.5rem; border-radius:99px; text-transform:uppercase; letter-spacing:0.5px; font-weight:600;">${moduleLabel}</span>
                                <span class="badge" style="background:${f.satisfied ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)'}; color:${f.satisfied ? '#10b981' : '#fca5a5'}; border:1px solid ${f.satisfied ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}; font-size:0.7rem;">
                                    ${f.satisfied ? '<i class="fas fa-thumbs-up"></i> Satisfied' : '<i class="fas fa-thumbs-down"></i> Not Satisfied'}
                                </span>
                                <span style="font-size:0.85rem; color:var(--text-3);">${new Date(f.created_at + 'Z').toLocaleString()}</span>
                            </div>
                        </div>
                        <p style="color:var(--text-2); line-height:1.5;">${f.comment ? `"${f.comment}"` : '<i style="color:var(--text-3)">No comment provided</i>'}</p>
                    </div>
                `}).join('');
            }
        } catch(err) {
            console.error("Failed to load admin dashboard:", err);
            alert("Error loading admin data.");
        }

        // 4. Load new analytics sections (non-blocking)
        try {
            const [usageRes, heatRes, healthRes] = await Promise.all([
                fetch('/api/admin/usage-analytics'),
                fetch('/api/admin/activity-heatmap'),
                fetch('/api/admin/system-health')
            ]);
            renderUsageChart(await usageRes.json());
            renderHeatmap(await heatRes.json());
            renderSystemHealth(await healthRes.json());
        } catch(e) { console.error('Analytics load error:', e); }

        // 5. Load user directory
        loadUserDirectory();
    }

    let satChart = null;
    function renderFeedbackBarChart(fbStats) {
        const ctx = document.getElementById('satisfactionChart').getContext('2d');
        if (satChart) satChart.destroy();

        const labels = ['Sentence Prediction', 'Video Cloning', 'Audio Cloning'];
        const keys   = ['sentence_prediction', 'video_cloning', 'audio_cloning'];
        const likes    = keys.map(k => fbStats[k]?.likes    || 0);
        const dislikes = keys.map(k => fbStats[k]?.dislikes || 0);

        satChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Like',
                        data: likes,
                        backgroundColor: '#10b981',
                        borderRadius: 6,
                        barPercentage: 0.5,
                        categoryPercentage: 0.6
                    },
                    {
                        label: 'Dislike',
                        data: dislikes,
                        backgroundColor: '#ef4444',
                        borderRadius: 6,
                        barPercentage: 0.5,
                        categoryPercentage: 0.6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        grid: { color: 'rgba(255,255,255,0.04)' },
                        ticks: { color: '#8b95a8', font: { family: 'DM Sans', size: 12 } }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255,255,255,0.06)' },
                        ticks: { color: '#8b95a8', stepSize: 1, font: { family: 'DM Sans' } },
                        title: { display: true, text: 'Vote Count', color: '#55616e', font: { family: 'Syne', size: 13, weight: 600 } }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: { color: '#8b95a8', font: { family: 'DM Sans' }, usePointStyle: true, pointStyle: 'rectRounded', padding: 18 }
                    },
                    tooltip: {
                        backgroundColor: '#161b27',
                        borderColor: 'rgba(255,255,255,0.1)',
                        borderWidth: 1,
                        titleColor: '#f0f4ff',
                        bodyColor: '#8b95a8'
                    }
                }
            }
        });
    }

    /* ── Usage Analytics Line Chart ── */
    let usageChartObj = null;
    function renderUsageChart(data) {
        const ctx = document.getElementById('usageChart').getContext('2d');
        if (usageChartObj) usageChartObj.destroy();
        const labels = data.map(d => d.day);
        usageChartObj = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: 'Predictions', data: data.map(d => d.predictions), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2 },
                    { label: 'Voice Clones', data: data.map(d => d.clones), borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)', fill: true, tension: 0.35, pointRadius: 3, borderWidth: 2 },
                    { label: 'Total', data: data.map(d => d.total), borderColor: '#8b5cf6', backgroundColor: 'rgba(139,92,246,0.05)', fill: false, tension: 0.35, pointRadius: 2, borderWidth: 1.5, borderDash: [5,3] }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#8b95a8', font: { size: 10 }, maxRotation: 45 } },
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { color: '#8b95a8', stepSize: 1 } }
                },
                plugins: {
                    legend: { position: 'top', labels: { color: '#8b95a8', font: { family: 'DM Sans' }, usePointStyle: true, padding: 15 } },
                    tooltip: { backgroundColor: '#161b27', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, titleColor: '#f0f4ff', bodyColor: '#8b95a8' }
                }
            }
        });
    }

    /* ── Activity Heatmap ── */
    function renderHeatmap(matrix) {
        const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        const maxVal = Math.max(1, ...matrix.flat());
        let html = '<div style="display:grid; grid-template-columns:40px repeat(24, 1fr); gap:2px; font-size:0.65rem;">';
        // Header row
        html += '<div></div>';
        for (let h = 0; h < 24; h++) html += `<div style="text-align:center; color:var(--text-3); padding:2px 0;">${h}</div>`;
        // Data rows
        for (let d = 0; d < 7; d++) {
            html += `<div style="color:var(--text-3); display:flex; align-items:center; font-weight:500;">${days[d]}</div>`;
            for (let h = 0; h < 24; h++) {
                const val = matrix[d][h];
                const intensity = val / maxVal;
                const bg = val === 0 ? 'rgba(255,255,255,0.03)' : `rgba(59,130,246,${0.15 + intensity * 0.7})`;
                html += `<div style="background:${bg}; border-radius:3px; aspect-ratio:1; display:flex; align-items:center; justify-content:center; color:${intensity > 0.5 ? '#fff' : 'var(--text-3)'}; font-weight:${val ? 600 : 400}; min-height:22px;" title="${days[d]} ${h}:00 — ${val} activities">${val || ''}</div>`;
            }
        }
        html += '</div>';
        document.getElementById('heatmapContainer').innerHTML = html;
    }

    /* ── System Health ── */
    function renderSystemHealth(h) {
        const statusDot = (ok) => `<span style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${ok ? '#10b981' : '#ef4444'}; margin-right:6px;"></span>`;
        const bar = (pct, color) => `<div style="background:rgba(255,255,255,0.06); border-radius:6px; height:10px; overflow:hidden; flex:1;"><div style="width:${pct}%; height:100%; background:${color}; border-radius:6px; transition:width 0.5s ease;"></div></div>`;
        const barColor = (pct) => pct > 85 ? '#ef4444' : pct > 60 ? '#f59e0b' : '#10b981';

        document.getElementById('systemHealthContainer').innerHTML = `
            <div style="display:flex; flex-direction:column; gap:1rem;">
                <div style="font-size:0.85rem; color:var(--text-2); font-weight:500;">Model Status</div>
                <div style="display:flex; flex-wrap:wrap; gap:0.75rem;">
                    <span style="font-size:0.8rem; color:var(--text-2);">${statusDot(h.lip_model_loaded)}Lip Reading Model</span>
                    <span style="font-size:0.8rem; color:var(--text-2);">${statusDot(h.tts_model_loaded)}TTS Model</span>
                    <span style="font-size:0.8rem; color:var(--text-2);">${statusDot(h.voice_engine_loaded)}Voice Engine</span>
                </div>
                <div style="margin-top:0.5rem;">
                    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem;">
                        <span style="font-size:0.8rem; color:var(--text-3); min-width:55px;">RAM</span>
                        ${bar(h.memory.percent, barColor(h.memory.percent))}
                        <span style="font-size:0.75rem; color:var(--text-3); min-width:90px; text-align:right;">${h.memory.used_gb}/${h.memory.total_gb} GB</span>
                    </div>
                    <div style="display:flex; align-items:center; gap:0.75rem; margin-bottom:0.75rem;">
                        <span style="font-size:0.8rem; color:var(--text-3); min-width:55px;">Disk</span>
                        ${bar(h.disk.percent, barColor(h.disk.percent))}
                        <span style="font-size:0.75rem; color:var(--text-3); min-width:90px; text-align:right;">${h.disk.used_gb}/${h.disk.total_gb} GB</span>
                    </div>
                </div>
                <div style="display:flex; gap:1.5rem; font-size:0.8rem; color:var(--text-3); border-top:1px solid rgba(255,255,255,0.05); padding-top:0.75rem;">
                    <span><i class="fas fa-upload"></i> Uploads: ${h.uploads_size_mb} MB</span>
                    <span><i class="fas fa-file-video"></i> Outputs: ${h.outputs_size_mb} MB</span>
                </div>
            </div>`;
    }

    /* ── User Directory ── */
    async function loadUserDirectory() {
        const search = document.getElementById('userSearchInput')?.value || '';
        const filter = document.getElementById('userFilterSelect')?.value || '';
        try {
            const res = await fetch(`/api/admin/users?search=${encodeURIComponent(search)}&filter=${filter}`);
            const users = await res.json();
            const tbody = document.getElementById('userDirectoryTable');
            if (!users.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:2rem; color:var(--text-3);">No users found.</td></tr>';
                return;
            }
            tbody.innerHTML = users.map(u => `
                <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                    <td style="padding:0.8rem 1.25rem; color:var(--primary); font-family:monospace;">${u.email}</td>
                    <td style="padding:0.8rem 1.25rem; color:var(--text-3); font-size:0.8rem;">${new Date(u.created_at + 'Z').toLocaleDateString()}</td>
                    <td style="padding:0.8rem 1.25rem; color:var(--text-3); font-size:0.8rem;">${u.last_login ? new Date(u.last_login + 'Z').toLocaleString() : '<i>Never</i>'}</td>
                    <td style="padding:0.8rem 1.25rem; font-weight:600;">${u.total_projects}</td>
                    <td style="padding:0.8rem 1.25rem; font-weight:600;">${u.total_feedback}</td>
                    <td style="padding:0.8rem 1.25rem;">
                        <span style="font-size:0.7rem; padding:0.15rem 0.5rem; border-radius:99px; font-weight:600; letter-spacing:0.5px;
                            background:${u.is_banned ? 'rgba(239,68,68,0.1)' : 'rgba(16,185,129,0.1)'};
                            color:${u.is_banned ? '#fca5a5' : '#34d399'};
                            border:1px solid ${u.is_banned ? 'rgba(239,68,68,0.2)' : 'rgba(16,185,129,0.2)'};
                        ">${u.is_banned ? 'BANNED' : 'ACTIVE'}</span>
                    </td>
                    <td style="padding:0.8rem 1.25rem;">
                        <button onclick="toggleBanUser(${u.id})" class="header-btn" style="padding:0.3rem 0.75rem; font-size:0.75rem;
                            border-color:${u.is_banned ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'};
                            color:${u.is_banned ? '#34d399' : '#fca5a5'};
                        ">
                            <i class="fas ${u.is_banned ? 'fa-unlock' : 'fa-ban'}"></i> ${u.is_banned ? 'Unban' : 'Ban'}
                        </button>
                    </td>
                </tr>
            `).join('');
        } catch(e) { console.error('User directory error:', e); }
    }

    async function toggleBanUser(userId) {
        if (!confirm('Are you sure you want to change this user's status?')) return;
        try {
            const res = await fetch(`/api/admin/user/${userId}/ban`, { method: 'POST' });
            const data = await res.json();
            if (data.success) loadUserDirectory();
            else alert('Error: ' + data.error);
        } catch(e) { alert('Failed to update user status.'); }
    }

    /* ── Result rendering ──────────────────────────────────── */
    function clearResult(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = 'result-panel';
        el.innerHTML = '';
    }

    function showResultError(id, msg) {
        const el = document.getElementById(id);
        if (!el) return;
        el.className = 'result-panel error';
        el.innerHTML = `
            <div class="result-error-head">
                <i class="fas fa-exclamation-triangle"></i> Error
            </div>
            <div style="color:var(--text-2);font-size:.875rem;margin-top:0.25rem;">${msg}</div>`;
    }

    function showResultSuccess(id, data, mode) {
        const el = document.getElementById(id);
        if (!el) return;

        const confPct  = (data.confidence * 100).toFixed(1);
        const isPred   = mode === 'prediction';
        const isFull   = mode === 'full';

        /* ── uploaded video blob URL for preview ── */
        const uploadedVideoFile = isPred ? selPredVideo : selFullVideo;
        const uploadedVideoURL  = uploadedVideoFile ? URL.createObjectURL(uploadedVideoFile) : null;

        /* ── header: tag + sentence + confidence ── */
        let html = `
            <div class="result-tag">
                <i class="fas fa-check-circle"></i>
                ${isFull ? 'Pipeline Complete' : 'Prediction Complete'}
            </div>`;

        if (data.warning) {
            html += `
            <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); color: #fcd34d; padding: 0.75rem; border-radius: var(--radius-sm); margin-bottom: 1rem; font-size: 0.85rem;">
                <i class="fas fa-exclamation-triangle"></i> <strong>Warning:</strong> ${data.warning}
            </div>`;
        }

        html += `
            <div class="result-sentence">"${data.predicted_sentence}"</div>
            <div class="result-confidence">
                Confidence &nbsp;<span class="conf-pill">${confPct}%</span>
            </div>`;

        /* ── probability bars ── */
        // Removed as requested by the user

        /* ── PREDICTION ONLY: show uploaded video ── */
        if (isPred && uploadedVideoURL) {
            html += `
            <div class="media-section">
                <div class="media-section-title">Input Video Preview</div>
                <div class="media-grid single">
                    <div class="media-block">
                        <div class="media-block-header">
                            <i class="fas fa-film"></i> Uploaded Video
                        </div>
                        <div class="media-block-body">
                            <video controls>
                                <source src="${uploadedVideoURL}">
                                Your browser does not support video playback.
                            </video>
                        </div>
                    </div>
                </div>
            </div>`;
        }

        /* ── FULL PIPELINE: show uploaded video + cloned audio + output video ── */
        if (isFull) {
            /* row 1: uploaded video + cloned audio */
            html += `<div class="media-section"><div class="media-section-title">Media Results</div>`;

            /* determine layout: if we have both input video and audio, 2-col */
            const hasAudio  = !!data.audio_path;
            const hasOutVid = !!data.video_path;
            const colCount  = (uploadedVideoURL && hasAudio) ? 2 : 1;

            html += `<div class="media-grid ${colCount === 1 ? 'single' : ''}">`;

            /* uploaded video */
            if (uploadedVideoURL) {
                html += `
                <div class="media-block">
                    <div class="media-block-header"><i class="fas fa-film"></i> Input Video</div>
                    <div class="media-block-body">
                        <video controls>
                            <source src="${uploadedVideoURL}">
                        </video>
                    </div>
                </div>`;
            }

            /* cloned audio */
            if (hasAudio) {
                const af = data.audio_path.split('/').pop();
                html += `
                <div class="media-block">
                    <div class="media-block-header"><i class="fas fa-music"></i> Cloned Audio</div>
                    <div class="media-block-body">
                        <audio controls>
                            <source src="/download/audio/${af}" type="audio/wav">
                            Your browser does not support audio playback.
                        </audio>
                    </div>
                </div>`;
            }

            html += `</div>`; /* close media-grid */

            /* output video — full width below */
            if (hasOutVid) {
                const vf = data.video_path.split('/').pop();
                html += `
                <div style="margin-top:1rem;">
                    <div class="media-block">
                        <div class="media-block-header"><i class="fas fa-clapperboard"></i> Output Video with Cloned Voice</div>
                        <div class="media-block-body">
                            <video controls>
                                <source src="/download/video/${vf}" type="video/mp4">
                                Your browser does not support video playback.
                            </video>
                        </div>
                    </div>
                </div>`;
            }

            html += `</div>`; /* close media-section */

            /* ── Downloads section (full pipeline only) ── */
            if (hasAudio || hasOutVid || uploadedVideoURL) {
                html += `
                <div class="downloads-section">
                    <div class="downloads-section-title"><i class="fas fa-download"></i> &nbsp;Downloads</div>
                    <div class="downloads-row">`;

                if (uploadedVideoURL && uploadedVideoFile) {
                    html += `
                        <a class="dl-btn orange" href="${uploadedVideoURL}" download="${uploadedVideoFile.name}">
                            <i class="fas fa-film"></i> Input Video
                        </a>`;
                }
                if (hasAudio) {
                    const af = data.audio_path.split('/').pop();
                    html += `
                        <a class="dl-btn" href="/download/audio/${af}" download>
                            <i class="fas fa-file-audio"></i> Cloned Audio
                        </a>`;
                }
                if (hasOutVid) {
                    const vf = data.video_path.split('/').pop();
                    html += `
                        <a class="dl-btn green" href="/download/video/${vf}" download>
                            <i class="fas fa-file-video"></i> Output Video
                        </a>`;
                }

                html += `</div></div>`; /* close downloads-row + downloads-section */
            }
        }

        /* ── Feedback section ── */
        const moduleTypeMap = { 'prediction': 'sentence_prediction', 'full': 'video_cloning' };
        const currentModuleType = moduleTypeMap[mode] || 'sentence_prediction';

        if (data.project_id) {
            html += `
            <div class="feedback-section" style="margin-top:2rem; padding-top:1.5rem; border-top:1px solid rgba(255,255,255,0.1);">
                <h4 style="font-size:1rem; color:var(--text-2); margin-bottom:1rem; text-align:center;"><i class="fas fa-comment-dots"></i> Provide Feedback</h4>
                <div id="feedbackContainer_${data.project_id}">
                    <p style="font-size:0.9rem; color:var(--text-2); margin-bottom:0.75rem; text-align:center;">Are you satisfied with the output generated?</p>
                    <div style="display:flex; justify-content:center; gap:1rem; margin-bottom:1.25rem;">
                        <button id="likeBtn_${data.project_id}" onclick="selectSatisfaction(${data.project_id}, 1, '${currentModuleType}')" class="header-btn" style="padding:0.65rem 1.5rem; border-color:rgba(16,185,129,0.3); color:#34d399; font-weight:600; transition:all 0.2s ease;">
                            <i class="fas fa-thumbs-up"></i> Like
                        </button>
                        <button id="dislikeBtn_${data.project_id}" onclick="selectSatisfaction(${data.project_id}, 0, '${currentModuleType}')" class="header-btn" style="padding:0.65rem 1.5rem; border-color:rgba(239,68,68,0.3); color:#fca5a5; font-weight:600; transition:all 0.2s ease;">
                            <i class="fas fa-thumbs-down"></i> Dislike
                        </button>
                    </div>
                    <textarea id="feedbackText_${data.project_id}" class="form-input" rows="2" placeholder="Tell us your thoughts (optional)..." style="margin-bottom:0.75rem;"></textarea>
                    <button onclick="finalSubmitFeedback(${data.project_id})" class="login-btn" style="max-width:220px; padding:0.6rem 1.25rem; font-size:0.875rem;">
                        <i class="fas fa-paper-plane"></i> Submit Feedback
                    </button>
                </div>
            </div>`;
        }

        el.className = 'result-panel success';
        el.innerHTML = html;
    }

    let lastSatisfaction = 1;
    let lastModuleType = 'sentence_prediction';

    function selectSatisfaction(projectId, isSatisfied, moduleType) {
        lastSatisfaction = isSatisfied;
        lastModuleType = moduleType || 'sentence_prediction';

        // Highlight selected button, dim the other
        const likeBtn = document.getElementById('likeBtn_' + projectId);
        const dislikeBtn = document.getElementById('dislikeBtn_' + projectId);
        if (isSatisfied) {
            likeBtn.style.background = 'rgba(16,185,129,0.2)';
            likeBtn.style.borderColor = '#10b981';
            likeBtn.style.transform = 'scale(1.05)';
            dislikeBtn.style.background = 'transparent';
            dislikeBtn.style.borderColor = 'rgba(239,68,68,0.3)';
            dislikeBtn.style.transform = 'scale(1)';
        } else {
            dislikeBtn.style.background = 'rgba(239,68,68,0.2)';
            dislikeBtn.style.borderColor = '#ef4444';
            dislikeBtn.style.transform = 'scale(1.05)';
            likeBtn.style.background = 'transparent';
            likeBtn.style.borderColor = 'rgba(16,185,129,0.3)';
            likeBtn.style.transform = 'scale(1)';
        }
    }

    async function finalSubmitFeedback(projectId) {
        const currentUserObj = localStorage.getItem('currentUser');
        if (!currentUserObj) {
            alert("You must be logged in to submit feedback.");
            return;
        }
        const user = JSON.parse(currentUserObj);
        const textEl = document.getElementById('feedbackText_' + projectId);
        const comment = textEl ? textEl.value.trim() : "";

        try {
            const res = await fetch('/api/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    user_id: user.id, 
                    project_id: projectId, 
                    module_type: lastModuleType,
                    comment: comment,
                    satisfied: lastSatisfaction
                })
            });
            const data = await res.json();
            if(data.success) {
                document.getElementById('feedbackContainer_' + projectId).innerHTML = '<div style="color:var(--success); font-weight:600; padding:1rem; background:rgba(16,185,129,0.1); border-radius:8px; text-align:center;"><i class="fas fa-check-circle"></i> Thank you for your feedback!</div>';
            } else {
                alert("Failed to submit feedback: " + (data.error || "Unknown error"));
            }
        } catch(err) {
            alert("Error communicating with server.");
        }
    }

    /* ── Init ──────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('loginPage').style.display = 'flex';
        document.getElementById('dashboardPage').style.display = 'none';
    });
