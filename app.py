# app_flask.py
import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'  # Fix OpenMP conflict

from flask import Flask, render_template, request, send_file, flash, redirect, jsonify, url_for, session
from scripts.transcribe import transcribe_video
from scripts.generate_srt import segments_to_srt
from scripts.rewrite_captions_gemini import rewrite_captions
from scripts.overlay import overlay_captions
from database import init_db, create_user, verify_user, get_user_by_id, save_video_record, get_all_user_videos
import threading
import webbrowser
import secrets
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# Persistent secret key (stored in file to survive restarts)
SECRET_KEY_FILE = '.flask_secret_key'
if os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE, 'r') as f:
        app.secret_key = f.read().strip()
else:
    # Generate new key and save it
    app.secret_key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(app.secret_key)

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_EXTENSIONS'] = ['.mp4', '.mov', '.avi', '.mkv']
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Better session security
app.config['SESSION_COOKIE_HTTPONLY'] = True    # Prevent XSS attacks
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)  # Session lasts 2 hours

# Create output directory if it doesn't exist
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Initialize database
init_db()

# Login decorator (optional - user can use without login)
def login_optional(f):
    """Decorator that doesn't require login but passes user info if logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """Decorator for routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('⚠️ Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Authentication Routes
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        success, user = verify_user(username, password)
        if success:
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f"✅ Welcome back, {user['username']}!", "success")
            return redirect(url_for('index'))
        else:
            flash("❌ Invalid username or password", "error")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        # Validation
        if password != confirm_password:
            flash("❌ Passwords do not match!", "error")
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash("❌ Password must be at least 6 characters long!", "error")
            return redirect(url_for('register'))
        
        success, result = create_user(username, email, password)
        if success:
            flash("✅ Account created successfully! Please login.", "success")
            return redirect(url_for('login'))
        else:
            flash(f"❌ {result}", "error")
    
    return render_template("register.html")

@app.route("/logout")
def logout():
    username = session.get('username', 'User')
    session.clear()
    flash(f"👋 Goodbye, {username}! See you next time.", "success")
    return redirect(url_for('login'))

@app.route("/history")
@login_required
def history():
    user_id = session.get('user_id')
    username = session.get('username')
    videos = get_all_user_videos(user_id)
    return render_template("history.html", videos=videos, username=username)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        video = request.files.get("video")
        style = request.form.get("style")
        lang = request.form.get("lang")
        speed = request.form.get("speed", "base")  # Default to "base" if not provided

        # Validate inputs
        if not video:
            flash("❌ Please upload a video!", "error")
            return redirect("/")
        
        # Check file extension
        filename = video.filename.lower()
        if not any(filename.endswith(ext) for ext in app.config['UPLOAD_EXTENSIONS']):
            flash("❌ Invalid file format! Please upload MP4, MOV, AVI, or MKV.", "error")
            return redirect("/")

        if not style or not lang:
            flash("❌ Please fill in all fields!", "error")
            return redirect("/")

        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(video.filename)[0]
        safe_base = "".join(c for c in base_name if c.isalnum() or c in ('_', '-'))[:50]
        
        # Create unique filenames
        unique_id = f"{safe_base}_{timestamp}"
        temp_path = f"temp_{unique_id}.mp4"
        output_video = os.path.join(app.config['OUTPUT_FOLDER'], f"captioned_{unique_id}.mp4")
        srt_path = os.path.join(app.config['OUTPUT_FOLDER'], f"captions_{unique_id}.srt")
        
        video.save(temp_path)

        try:
            import time
            total_start = time.time()
            
            print("\n" + "="*80)
            print("🎬 VIDEO PROCESSING PIPELINE STARTED")
            print("="*80)
            print(f"📹 Input file: {video.filename}")
            print(f"📊 File size: {os.path.getsize(temp_path) / 1024 / 1024:.2f} MB")
            print(f"🎨 Style: {style}")
            print(f"🌍 Language: {lang}")
            print(f"⚡ Speed: {speed}")
            print(f"� User: {session.get('username', 'Guest')}")
            print("="*80)
            
            # STEP 1: Whisper Transcription
            step1_start = time.time()
            segments = transcribe_video(temp_path, model_size=speed)
            step1_time = time.time() - step1_start
            
            if not segments:
                flash("❌ No transcription segments found!", "error")
                return redirect("/")

            # STEP 2: Gemini Caption Rewriting
            step2_start = time.time()
            print("\n" + "="*60)
            print("📝 GEMINI CAPTION REWRITING STARTED")
            print("="*60)
            print(f"📊 Total segments: {len(segments)}")
            print(f"🎨 Style: {style}")
            print(f"🌍 Language: {lang}")
            print("="*60)
            
            for i, seg in enumerate(segments, 1):
                seg_start = time.time()
                original_text = seg["text"]
                seg["text"] = rewrite_captions(seg["text"], style=style, lang=lang).text
                seg_time = time.time() - seg_start
                
                if i % 5 == 0 or i == len(segments):
                    avg_time = (time.time() - step2_start) / i
                    remaining = (len(segments) - i) * avg_time
                    print(f"\n📊 Progress: {i}/{len(segments)} ({i/len(segments)*100:.1f}%)")
                    print(f"   ⏱️  Avg time per segment: {avg_time:.2f}s")
                    print(f"   ⏳ Est. remaining: {remaining:.1f}s")
            
            step2_time = time.time() - step2_start
            print(f"\n✅ Caption rewriting complete in {step2_time:.1f}s")
            print(f"   Average: {step2_time/len(segments):.2f}s per segment")
            print("="*60 + "\n")

            # STEP 3: Generate SRT
            step3_start = time.time()
            print("="*60)
            print("📄 GENERATING SRT FILE")
            print("="*60)
            segments_to_srt(segments, srt_path)
            step3_time = time.time() - step3_start
            print(f"✅ SRT file created: {os.path.basename(srt_path)}")
            print(f"⏱️  Time: {step3_time:.2f}s")
            print("="*60 + "\n")

            # STEP 4: Overlay Captions
            step4_start = time.time()
            print("="*60)
            print("🎥 OVERLAYING CAPTIONS ON VIDEO")
            print("="*60)
            print(f"📹 Input: {os.path.basename(temp_path)}")
            print(f"📄 Captions: {os.path.basename(srt_path)}")
            print(f"📹 Output: {os.path.basename(output_video)}")
            print("🔄 Processing (this may take a while)...")
            overlay_captions(temp_path, srt_path, output_video)
            step4_time = time.time() - step4_start
            print(f"✅ Video overlay complete in {step4_time:.1f}s")
            print("="*60 + "\n")
            
            # Summary
            total_time = time.time() - total_start
            print("\n" + "="*80)
            print("✅ PROCESSING COMPLETE - SUMMARY")
            print("="*80)
            print(f"⏱️  Step 1 - Whisper Transcription: {step1_time:.1f}s ({step1_time/total_time*100:.1f}%)")
            print(f"⏱️  Step 2 - Gemini Rewriting: {step2_time:.1f}s ({step2_time/total_time*100:.1f}%)")
            print(f"⏱️  Step 3 - SRT Generation: {step3_time:.2f}s ({step3_time/total_time*100:.1f}%)")
            print(f"⏱️  Step 4 - Video Overlay: {step4_time:.1f}s ({step4_time/total_time*100:.1f}%)")
            print(f"{'─'*80}")
            print(f"⏱️  TOTAL TIME: {total_time:.1f}s ({total_time/60:.2f} minutes)")
            print(f"📊 Segments processed: {len(segments)}")
            print(f"📹 Output file: {os.path.basename(output_video)}")
            print(f"💾 Output size: {os.path.getsize(output_video) / 1024 / 1024:.2f} MB")
            print("="*80 + "\n")

            # Save to database if user is logged in
            if 'user_id' in session:
                save_video_record(
                    user_id=session['user_id'],
                    original_filename=video.filename,
                    video_file=f"captioned_{unique_id}.mp4",
                    srt_file=f"captions_{unique_id}.srt",
                    style=style,
                    language=lang
                )

            # Store result info in session with permanent flag
            session.permanent = True  # Make session persistent
            session['result'] = {
                'video_file': f"captioned_{unique_id}.mp4",
                'srt_file': f"captions_{unique_id}.srt",
                'original_name': video.filename,
                'style': style,
                'lang': lang,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'saved': 'user_id' in session  # Indicate if saved to history
            }

            return redirect(url_for('result'))

        except Exception as e:
            flash(f"⚠️ An error occurred: {str(e)}", "error")
            return redirect("/")

        finally:
            # Cleanup temporary file only
            if os.path.exists(temp_path):
                os.remove(temp_path)

    return render_template("index.html")


@app.route("/result")
def result():
    result_data = session.get('result')
    if not result_data:
        flash("❌ No result found. Please upload a video first.", "error")
        return redirect("/")
    return render_template("result.html", result=result_data)


@app.route("/download/<filename>")
def download(filename):
    file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        flash("❌ File not found!", "error")
        return redirect("/")


@app.route("/preview/<filename>")
def preview(filename):
    """Serve video file for preview (not download)"""
    file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if os.path.exists(file_path):
        return send_file(file_path, mimetype='video/mp4')
    else:
        flash("❌ File not found!", "error")
        return redirect("/")


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    # Open browser in a separate thread
    threading.Timer(1.0, open_browser).start()
    # Disable reloader to prevent threading issues
    app.run(debug=True, use_reloader=False)
