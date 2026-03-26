"""
EchoVox Lip Reading + Voice Cloning Web App
Provides web interface for video upload, sentence prediction, voice cloning, and video generation
"""

import os
import sys

# ── Environment fixes (must be set BEFORE importing torch / numpy) ────────
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"        # OpenMP duplicate‑lib guard
os.environ["OMP_NUM_THREADS"] = "1"                  # avoid thread over‑subscription

import tempfile
import time
import torch
import cv2
import subprocess
import shutil
from pathlib import Path
import uuid
import threading
import json
import sqlite3
import psutil
from flask import Flask, request, render_template, jsonify, send_file, g, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Import voice cloning engine (optional — needs Coqui TTS + C++ build tools)
try:
    from voice_cloning_engine import EchoVoxTTS, get_voice_engine, cleanup_voice_engine
    VOICE_CLONING_AVAILABLE = True
except ImportError as _vc_err:
    VOICE_CLONING_AVAILABLE = False
    EchoVoxTTS = None
    def get_voice_engine(): return None
    def cleanup_voice_engine(): pass
    print(f"[WARNING] Voice cloning unavailable: {_vc_err}")

# Add current directory to path for imports
sys.path.insert(0, ".")
from lip_reading_train import LipReadingModel, build_face_landmarker, extract_mouth_frames

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size
app.config['UPLOAD_FOLDER'] = 'temp_uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create folders if they don't exist
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'echovox_users.db')

def get_db():
    """Get a database connection for the current request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    """Create the users table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            predicted_sentence TEXT,
            video_file TEXT,
            audio_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            module_type TEXT NOT NULL DEFAULT 'sentence_prediction',
            comment TEXT,
            satisfied INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    # Migration guards for older DBs
    for col_sql in [
        'ALTER TABLE feedback ADD COLUMN satisfied INTEGER DEFAULT 1',
        "ALTER TABLE feedback ADD COLUMN module_type TEXT NOT NULL DEFAULT 'sentence_prediction'",
        'ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0',
        'ALTER TABLE users ADD COLUMN last_login TIMESTAMP',
    ]:
        try:
            conn.execute(col_sql)
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.close()

init_db()

# Global task tracker for SSE progress
TASKS = {}

# Allowed file extensions
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
ALLOWED_AUDIO_EXTENSIONS = {'wav', 'mp3', 'm4a', 'flac'}

# Global variables for models (lazy loading)
model = None
checkpoint_data = None
device = None
tts_model = None

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def load_lip_model():
    global model, checkpoint_data, device
    if model is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint_path = "checkpoints/best_model.pt"
        
        if not Path(checkpoint_path).exists():
            checkpoint_path = "checkpoints/final_model.pt"
        
        if not Path(checkpoint_path).exists():
            raise FileNotFoundError("No model checkpoint found in checkpoints/ directory")
        
        checkpoint_data = torch.load(checkpoint_path, map_location=device, weights_only=False)
        model = LipReadingModel(checkpoint_data["cfg"]).to(device)
        model.load_state_dict(checkpoint_data["model_state"])
        model.eval()
        
        print(f"Lip model loaded from {checkpoint_path}")
        print(f"Device: {device}")

def load_tts_model():
    global tts_model
    if tts_model is None:
        # Use a default reference audio - you can modify this
        reference_audio = "reference_speaker.wav"
        if not Path(reference_audio).exists():
            # If no default reference audio, we'll handle this in the route
            print("Warning: Default reference audio file not found. Please provide reference_speaker.wav or upload audio file.")
            return None
        
        if not VOICE_CLONING_AVAILABLE:
            print("Warning: Voice cloning not available (TTS library not installed)")
            return None
        tts_model = EchoVoxTTS(voice_file=reference_audio)
        print("TTS model loaded successfully")

def predict_video(video_path):
    try:
        load_lip_model()
        
        # Get sentences from checkpoint
        if "sentences" in checkpoint_data:
            sentences = checkpoint_data["sentences"]
        elif "label_enc" in checkpoint_data:
            sentences = list(checkpoint_data["label_enc"].classes_)
        else:
            raise ValueError("Checkpoint has no label mapping")
        
        # MediaPipe landmarker
        lmk = None
        mp_path = checkpoint_data["cfg"].get("mediapipe_model", "face_landmarker.task")
        if Path(mp_path).exists():
            try:
                lmk = build_face_landmarker(mp_path)
            except Exception:
                pass
        
        # Extract frames and run inference
        frames = extract_mouth_frames(video_path, checkpoint_data["cfg"], lmk)
        if lmk:
            lmk.close()
        
        if frames is None:
            return {"error": "No face detected in video"}
        
        import torch.nn.functional as F
        x = torch.tensor(frames).permute(0, 3, 1, 2).unsqueeze(0).float().to(device)
        
        with torch.no_grad():
            probs = F.softmax(model(x), dim=1)[0]
        
        idx = probs.argmax().item()
        
        return {
            "predicted_sentence": sentences[idx],
            "confidence": round(probs[idx].item(), 4),
            "all_probs": {s: round(p.item(), 4) for s, p in zip(sentences, probs)}
        }
    
    except Exception as e:
        return {"error": str(e)}

def clone_voice(text, output_path, reference_audio=None):
    """
    Clone voice using XTTS engine
    
    Args:
        text: Text to synthesize
        output_path: Path to save output audio
        reference_audio: Path to reference audio file (optional)
    
    Returns:
        Path to generated audio file
    """
    if not VOICE_CLONING_AVAILABLE:
        raise RuntimeError("Voice cloning is unavailable — Coqui TTS library not installed.")
    if reference_audio:
        # Use provided reference audio
        tts = EchoVoxTTS(voice_file=reference_audio)
        audio_path = tts.synthesize(text, output_path=output_path, play_audio=False)
    else:
        # Use default TTS model if available
        load_tts_model()
        if tts_model is None:
            raise FileNotFoundError("No reference audio available. Please upload a reference audio file.")
        audio_path = tts_model.synthesize(text, output_path=output_path, play_audio=False)
    return audio_path

def combine_video_audio(video_path, audio_path, output_path):
    """Combine video with new audio using ffmpeg"""
    try:
        # Try ffmpeg first
        cmd = [
            'ffmpeg', '-i', video_path, '-i', audio_path,
            '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0',
            '-y', output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            return output_path
        else:
            print(f"FFmpeg error: {result.stderr}")
            raise Exception("FFmpeg failed to combine video and audio")
    
    except FileNotFoundError:
        # Fallback to OpenCV if ffmpeg not available
        try:
            cap = cv2.VideoCapture(video_path)
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)
            
            cap.release()
            out.release()
            
            # Note: This fallback doesn't actually add audio, just copies video
            print("Warning: FFmpeg not available. Generated video has no audio.")
            return output_path
            
        except Exception as e:
            raise Exception(f"Video combination failed: {str(e)}")

# HTML Template is now in templates/index.html
# CSS is in static/css/style.css
# JS is in static/js/app.js

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process', methods=['POST'])
def process():
    mode = request.form.get('mode', 'prediction')
    
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"})
    
    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({"error": "No video file selected"})
    
    if not allowed_file(video_file.filename, ALLOWED_VIDEO_EXTENSIONS):
        return jsonify({"error": "Invalid video file type"})
    
    audio_file = None
    if mode == 'full' and 'audio' in request.files:
        audio_file = request.files['audio']
        if audio_file.filename != '' and not allowed_file(audio_file.filename, ALLOWED_AUDIO_EXTENSIONS):
            return jsonify({"error": "Invalid audio file type"})
    
    try:
        task_id = str(uuid.uuid4())
        task_dir = os.path.abspath(os.path.join(app.config['UPLOAD_FOLDER'], task_id))
        os.makedirs(task_dir, exist_ok=True)
        
        video_filename = secure_filename(video_file.filename)
        video_path = os.path.join(task_dir, video_filename)
        video_file.save(video_path)
        
        audio_path = None
        if audio_file and audio_file.filename != '':
            audio_filename = secure_filename(audio_file.filename)
            audio_path = os.path.join(task_dir, audio_filename)
            audio_file.save(audio_path)
            
        user_id = request.form.get('user_id')
        
        TASKS[task_id] = {
            "status": "running",
            "progress_msg": "Initializing pipeline...",
            "result": None,
            "error": None
        }
        
        # Start background thread
        thread = threading.Thread(target=run_pipeline, args=(task_id, mode, video_path, audio_path, user_id, task_dir))
        thread.daemon = True
        thread.start()
        
        return jsonify({"task_id": task_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_pipeline(task_id, mode, video_path, audio_path, user_id, task_dir):
    try:
        import traceback as _tb
        TASKS[task_id]["progress_msg"] = "Step 1/3: Reading lips from video..."
        prediction = predict_video(video_path)
        if "error" in prediction:
            TASKS[task_id]["error"] = prediction["error"]
            TASKS[task_id]["status"] = "error"
            return
            
        result = {
            "predicted_sentence": prediction["predicted_sentence"],
            "confidence": prediction["confidence"],
            "all_probs": prediction["all_probs"]
        }
        
        if mode == 'full':
            TASKS[task_id]["progress_msg"] = "Step 2/3: Loading Voice Model and cloning voice. This takes 1-2 minutes..."
            timestamp = int(time.time() * 1000)
            audio_output = os.path.abspath(os.path.join(app.config['OUTPUT_FOLDER'], f"cloned_audio_{timestamp}.wav"))
            
            try:
                TASKS[task_id]["progress_msg"] = "Step 2/3: Generating synthetic audio with XTTS-v2..."
                if audio_path:
                    clone_voice(prediction["predicted_sentence"], audio_output, reference_audio=audio_path)
                    result["audio_path"] = f"cloned_audio_{timestamp}.wav"
                else:
                    try:
                        clone_voice(prediction["predicted_sentence"], audio_output)
                        result["audio_path"] = f"cloned_audio_{timestamp}.wav"
                    except FileNotFoundError:
                        print("No reference audio available for voice cloning")
                        
                if "audio_path" in result:
                    TASKS[task_id]["progress_msg"] = "Step 3/3: Fusing cloned audio with silent video..."
                    video_output = os.path.abspath(os.path.join(app.config['OUTPUT_FOLDER'], f"final_video_{timestamp}.mp4"))
                    try:
                        final_video = combine_video_audio(video_path, audio_output, video_output)
                        result["video_path"] = f"final_video_{timestamp}.mp4"
                    except Exception as e:
                        print(f"Video combination failed: {str(e)}")
            except Exception as e:
                result["warning"] = f"Voice cloning failed: {str(e)}"
                
        # Save to SQLite History if logged in
        if user_id:
            try:
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute('INSERT INTO projects (user_id, type, predicted_sentence, video_file, audio_file) VALUES (?, ?, ?, ?, ?)',
                            (user_id, mode, result.get('predicted_sentence'), result.get('video_path'), result.get('audio_path')))
                result['project_id'] = cursor.lastrowid
                conn.commit()
                conn.close()
            except Exception as db_err:
                print("Failed to save to database:", db_err)

        TASKS[task_id]["result"] = result
        TASKS[task_id]["status"] = "complete"
    except MemoryError:
        TASKS[task_id]["error"] = "Out of memory while loading the voice model. Close other programs and try again."
        TASKS[task_id]["status"] = "error"
    except Exception as e:
        import traceback as _tb2
        tb_str = _tb2.format_exc()
        print(f"[run_pipeline] Exception: {tb_str}")
        TASKS[task_id]["error"] = str(e) or "An unexpected error occurred in the pipeline."
        TASKS[task_id]["status"] = "error"
    finally:
        # Clean up temporary files
        try:
            shutil.rmtree(task_dir, ignore_errors=True)
        except Exception:
            pass

@app.route('/stream/<task_id>')
def stream(task_id):
    def generate():
        last_ping = time.time()
        while True:
            task = TASKS.get(task_id)
            if not task:
                yield f"data: {json.dumps({'error': 'Task not found', 'status': 'error'})}\n\n"
                break

            yield f"data: {json.dumps(task)}\n\n"

            if task["status"] in ["complete", "error"]:
                time.sleep(1)  # Let the client process the final state
                if task_id in TASKS:
                    del TASKS[task_id]
                break

            # Send a keep-alive comment every 15 s to prevent proxy/browser timeout
            now = time.time()
            if now - last_ping >= 15:
                yield ": keep-alive\n\n"
                last_ping = now

            time.sleep(0.3)

    resp = Response(generate(), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    resp.headers['Connection'] = 'keep-alive'
    return resp

@app.route('/api/projects/<int:user_id>')
def get_user_projects(user_id):
    try:
        db = get_db()
        # Fetch descending by date
        rows = db.execute('SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
        projects = []
        for r in rows:
            projects.append({
                "id": r["id"],
                "type": r["type"],
                "predicted_sentence": r["predicted_sentence"],
                "video_file": r["video_file"],
                "audio_file": r["audio_file"],
                "created_at": r["created_at"]
            })
        return jsonify(projects)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/audio/<filename>')
def download_audio(filename):
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if os.path.exists(file_path):
            # Determine MIME type based on file extension
            if filename.endswith('.wav'):
                mimetype = 'audio/wav'
            elif filename.endswith('.mp3'):
                mimetype = 'audio/mpeg'
            else:
                mimetype = 'audio/wav'
            return send_file(file_path, as_attachment=True, download_name=filename, mimetype=mimetype)
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/video/<filename>')
def download_video(filename):
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required"})
    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters"})

    db = get_db()
    existing = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
    if existing:
        return jsonify({"success": False, "error": "An account with this email already exists"})

    db.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)',
               (email, generate_password_hash(password)))
    db.commit()
    return jsonify({"success": True})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    db = get_db()
    user = db.execute('SELECT id, password_hash, is_banned FROM users WHERE email = ?', (email,)).fetchone()
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"success": False, "error": "Invalid email or password"})
    
    if user['is_banned']:
        return jsonify({"success": False, "error": "Your account has been suspended by the administrator."})

    db.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
    db.commit()
    return jsonify({"success": True, "user_id": user['id'], "email": email})

@app.route('/admin/register', methods=['POST'])
def admin_register():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    db = get_db()
    
    # Restrict to only 1 admin account
    admin_count = db.execute('SELECT COUNT(*) as count FROM admins').fetchone()['count']
    if admin_count > 0:
        return jsonify({"success": False, "error": "Admin account already exists. Only one admin is allowed."})
        
    if not email or len(password) < 6:
        return jsonify({"success": False, "error": "Email and a 6+ char password required."})

    db.execute('INSERT INTO admins (email, password_hash) VALUES (?, ?)',
               (email, generate_password_hash(password)))
    db.commit()
    return jsonify({"success": True})

@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    db = get_db()
    admin = db.execute('SELECT id, password_hash FROM admins WHERE email = ?', (email,)).fetchone()
    if not admin or not check_password_hash(admin['password_hash'], password):
        return jsonify({"success": False, "error": "Invalid admin credentials"})

    return jsonify({"success": True, "admin_id": admin['id'], "email": email, "role": "admin"})

VALID_MODULE_TYPES = {'video_cloning', 'audio_cloning', 'sentence_prediction'}

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    data = request.get_json()
    user_id = data.get('user_id')
    comment = data.get('comment', '').strip()
    project_id = data.get('project_id')
    module_type = data.get('module_type', 'sentence_prediction')
    satisfied = data.get('satisfied', 1)
    
    if not user_id:
        return jsonify({"success": False, "error": "Missing user_id"})
    if module_type not in VALID_MODULE_TYPES:
        return jsonify({"success": False, "error": f"Invalid module_type. Must be one of: {', '.join(VALID_MODULE_TYPES)}"})
    if satisfied not in (0, 1, True, False):
        return jsonify({"success": False, "error": "satisfied must be 0 or 1"})
        
    db = get_db()
    db.execute(
        'INSERT INTO feedback (user_id, project_id, module_type, comment, satisfied) VALUES (?, ?, ?, ?, ?)',
        (user_id, project_id, module_type, comment, int(satisfied))
    )
    db.commit()
    return jsonify({"success": True})

@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    db = get_db()
    total_users = db.execute('SELECT COUNT(*) as c FROM users').fetchone()['c']
    total_projects = db.execute('SELECT COUNT(*) as c FROM projects').fetchone()['c']
    total_feedback = db.execute('SELECT COUNT(*) as c FROM feedback').fetchone()['c']
    total_clones = db.execute("SELECT COUNT(*) as c FROM projects WHERE type='full'").fetchone()['c']
    total_satisfied = db.execute('SELECT COUNT(*) as c FROM feedback WHERE satisfied = 1').fetchone()['c']
    total_unsatisfied = db.execute('SELECT COUNT(*) as c FROM feedback WHERE satisfied = 0').fetchone()['c']
    
    return jsonify({
        "total_users": total_users,
        "total_projects": total_projects,
        "total_feedback": total_feedback,
        "total_clones": total_clones,
        "total_satisfied": total_satisfied,
        "total_unsatisfied": total_unsatisfied
    })

@app.route('/api/admin/feedback-stats', methods=['GET'])
def get_admin_feedback_stats():
    """Returns likes/dislikes grouped by module_type for the admin bar chart."""
    db = get_db()
    rows = db.execute('''
        SELECT
            module_type,
            SUM(CASE WHEN satisfied = 1 THEN 1 ELSE 0 END) as likes,
            SUM(CASE WHEN satisfied = 0 THEN 1 ELSE 0 END) as dislikes
        FROM feedback
        GROUP BY module_type
    ''').fetchall()
    
    # Ensure all three modules are present even if no data
    result = {
        'video_cloning':       {'likes': 0, 'dislikes': 0},
        'audio_cloning':       {'likes': 0, 'dislikes': 0},
        'sentence_prediction': {'likes': 0, 'dislikes': 0},
    }
    for r in rows:
        mt = r['module_type']
        if mt in result:
            result[mt] = {'likes': r['likes'], 'dislikes': r['dislikes']}
    
    return jsonify(result)

@app.route('/api/admin/projects', methods=['GET'])
def get_admin_projects():
    db = get_db()
    # Join with users to get emails
    rows = db.execute('''
        SELECT p.id, p.type, p.predicted_sentence, p.created_at, u.email as user_email
        FROM projects p
        LEFT JOIN users u ON p.user_id = u.id
        ORDER BY p.created_at DESC LIMIT 100
    ''').fetchall()
    
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/feedback', methods=['GET'])
def get_admin_feedback():
    db = get_db()
    rows = db.execute('''
        SELECT f.id, f.module_type, f.comment, f.satisfied, f.created_at, u.email as user_email
        FROM feedback f
        LEFT JOIN users u ON f.user_id = u.id
        ORDER BY f.created_at DESC LIMIT 100
    ''').fetchall()
    
    return jsonify([dict(r) for r in rows])

# ── New Admin Analytics & User Management Endpoints ────────────

@app.route('/api/admin/usage-analytics', methods=['GET'])
def get_usage_analytics():
    """Daily project counts for last 30 days, grouped by type."""
    db = get_db()
    rows = db.execute('''
        SELECT DATE(created_at) as day,
               SUM(CASE WHEN type = 'prediction' THEN 1 ELSE 0 END) as predictions,
               SUM(CASE WHEN type = 'full' THEN 1 ELSE 0 END) as clones,
               COUNT(*) as total
        FROM projects
        WHERE created_at >= DATE('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    ''').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/activity-heatmap', methods=['GET'])
def get_activity_heatmap():
    """Hourly activity counts grouped by day-of-week (0=Sun..6=Sat) and hour (0-23)."""
    db = get_db()
    rows = db.execute('''
        SELECT CAST(strftime('%%w', created_at) AS INTEGER) as dow,
               CAST(strftime('%%H', created_at) AS INTEGER) as hour,
               COUNT(*) as count
        FROM projects
        GROUP BY dow, hour
    ''').fetchall()
    # Build 7x24 matrix
    heatmap = [[0]*24 for _ in range(7)]
    for r in rows:
        heatmap[r['dow']][r['hour']] = r['count']
    return jsonify(heatmap)

@app.route('/api/admin/system-health', methods=['GET'])
def get_system_health():
    """Model load status, memory usage, and disk space."""
    mem = psutil.virtual_memory()
    disk = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__)))
    return jsonify({
        "lip_model_loaded": model is not None,
        "tts_model_loaded": tts_model is not None,
        "voice_engine_loaded": get_voice_engine() is not None,
        "memory": {
            "total_gb": round(mem.total / (1024**3), 1),
            "used_gb": round(mem.used / (1024**3), 1),
            "percent": mem.percent
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "percent": round(disk.used / disk.total * 100, 1)
        },
        "uploads_size_mb": round(sum(f.stat().st_size for f in Path(app.config['UPLOAD_FOLDER']).rglob('*') if f.is_file()) / (1024**2), 1) if Path(app.config['UPLOAD_FOLDER']).exists() else 0,
        "outputs_size_mb": round(sum(f.stat().st_size for f in Path(app.config['OUTPUT_FOLDER']).rglob('*') if f.is_file()) / (1024**2), 1) if Path(app.config['OUTPUT_FOLDER']).exists() else 0
    })

@app.route('/api/admin/users', methods=['GET'])
def get_admin_users():
    """Full user list with activity stats, search, and filter."""
    db = get_db()
    search = request.args.get('search', '').strip().lower()
    filter_level = request.args.get('filter', '')  # active, inactive, banned
    
    query = '''
        SELECT u.id, u.email, u.is_banned, u.created_at, u.last_login,
               COUNT(DISTINCT p.id) as total_projects,
               COUNT(DISTINCT f.id) as total_feedback
        FROM users u
        LEFT JOIN projects p ON u.id = p.user_id
        LEFT JOIN feedback f ON u.id = f.user_id
    '''
    conditions = []
    params = []
    
    if search:
        conditions.append('LOWER(u.email) LIKE ?')
        params.append(f'%{search}%')
    if filter_level == 'banned':
        conditions.append('u.is_banned = 1')
    elif filter_level == 'active':
        conditions.append('u.last_login IS NOT NULL AND u.is_banned = 0')
    elif filter_level == 'inactive':
        conditions.append('(u.last_login IS NULL) AND u.is_banned = 0')
    
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    
    query += ' GROUP BY u.id ORDER BY u.created_at DESC'
    rows = db.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/user/<int:user_id>/ban', methods=['POST'])
def toggle_ban_user(user_id):
    """Toggle the ban status of a user."""
    db = get_db()
    user = db.execute('SELECT id, is_banned FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        return jsonify({"success": False, "error": "User not found"})
    new_status = 0 if user['is_banned'] else 1
    db.execute('UPDATE users SET is_banned = ? WHERE id = ?', (new_status, user_id))
    db.commit()
    return jsonify({"success": True, "is_banned": new_status})

def close_db(error):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.route('/health')
def health():
    _ve = None
    if VOICE_CLONING_AVAILABLE:
        try:
            from voice_cloning_engine import _voice_engine as _ve
        except ImportError:
            pass
    return jsonify({
        "status": "healthy",
        "lip_model_loaded": model is not None,
        "tts_model_loaded": tts_model is not None,
        "voice_engine_loaded": _ve is not None
    })

@app.teardown_appcontext
def cleanup(error):
    """Cleanup resources on app teardown"""
    pass

@app.route('/shutdown')
def shutdown():
    """Cleanup voice engine on shutdown"""
    cleanup_voice_engine()
    return jsonify({"status": "shutdown_complete"})

if __name__ == '__main__':
    print("Starting EchoVox Lip Reading + Voice Cloning Web App...")
    print("Open http://localhost:5000 in your browser")
    print("\nFeatures:")
    print("- Lip reading prediction from video")
    print("- Voice cloning with custom reference audio")
    print("- Video generation with cloned voice")
    print("- Download audio and video outputs")
    # use_reloader=False is critical: the stat-reloader restarts the child process
    # mid-request and kills all active SSE streams (Lost connection error).
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False, threaded=True)
