# app_flask.py
from flask import Flask, render_template, request, send_file, flash, redirect, jsonify, url_for, session
from scripts.transcribe import transcribe_video
from scripts.generate_srt import segments_to_srt
from scripts.rewrite_captions_gemini import rewrite_captions
from scripts.overlay import overlay_captions
import os
import threading
import webbrowser
import secrets
from datetime import datetime

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Secure secret key
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_EXTENSIONS'] = ['.mp4', '.mov', '.avi', '.mkv']
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create output directory if it doesn't exist
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        video = request.files.get("video")
        style = request.form.get("style")
        lang = request.form.get("lang")

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
            segments = transcribe_video(temp_path)
            if not segments:
                flash("❌ No transcription segments found!", "error")
                return redirect("/")

            for seg in segments:
                seg["text"] = rewrite_captions(seg["text"], style=style, lang=lang).text

            segments_to_srt(segments, srt_path)
            overlay_captions(temp_path, srt_path, output_video)

            # Store result info in session
            session['result'] = {
                'video_file': f"captioned_{unique_id}.mp4",
                'srt_file': f"captions_{unique_id}.srt",
                'original_name': video.filename,
                'style': style,
                'lang': lang,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    # Open browser in a separate thread
    threading.Timer(1.0, open_browser).start()
    app.run(debug=True)
