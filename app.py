# app_flask.py
from flask import Flask, render_template, request, send_file, flash, redirect
from scripts.transcribe import transcribe_video
from scripts.generate_srt import segments_to_srt
from scripts.rewrite_captions_gemini import rewrite_captions
from scripts.overlay import overlay_captions
import os
import threading
import webbrowser

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for flash messages

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        video = request.files.get("video")
        style = request.form.get("style")
        lang = request.form.get("lang")

        if not video:
            flash("❌ Please upload a video!")
            return redirect("/")

        temp_path = f"temp_{video.filename}"
        video.save(temp_path)

        try:
            segments = transcribe_video(temp_path)
            if not segments:
                flash("❌ No transcription segments found!")
                return redirect("/")

            for seg in segments:
                seg["text"] = rewrite_captions(seg["text"], style=style, lang=lang).text

            srt_path = "output.srt"
            segments_to_srt(segments, srt_path)

            output_video = "output.mp4"
            overlay_captions(temp_path, srt_path, output_video)

            return send_file(output_video, as_attachment=True)

        except Exception as e:
            flash(f"⚠️ An error occurred: {str(e)}")
            return redirect("/")

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if os.path.exists("output.srt"):
                os.remove("output.srt")

    return render_template("index.html")


def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")


if __name__ == "__main__":
    # Open browser in a separate thread
    threading.Timer(1.0, open_browser).start()
    app.run(debug=True)
