from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
import pysrt
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import textwrap

def create_text_image(text, width, height, fontsize=40):
    """Create an image with text using PIL"""
    # Create transparent image
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Try to use a common font, fallback to default
    try:
        # Try common Windows fonts
        font = ImageFont.truetype("arial.ttf", fontsize)
    except:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", fontsize)
        except:
            # Fallback to default font
            font = ImageFont.load_default()
    
    # Wrap text to fit width
    max_chars_per_line = int(width / (fontsize * 0.6))
    wrapped_text = textwrap.fill(text, width=max_chars_per_line)
    
    # Get text bounding box
    bbox = draw.textbbox((0, 0), wrapped_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Calculate position to center text
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    # Draw background rectangle
    padding = 10
    draw.rectangle(
        [x - padding, y - padding, x + text_width + padding, y + text_height + padding],
        fill=(0, 0, 0, 153)  # Semi-transparent black
    )
    
    # Draw text
    draw.text((x, y), wrapped_text, font=font, fill=(255, 255, 255, 255))
    
    return np.array(img)

def overlay_captions(video_path, srt_path, output_path="output.mp4"):
    video = VideoFileClip(video_path)
    subs = pysrt.open(srt_path)
    
    txt_clips = []
    caption_height = int(video.h * 0.15)  # 15% of video height for captions
    
    for sub in subs:
        # Create text image
        text_img = create_text_image(
            sub.text, 
            video.w, 
            caption_height,
            fontsize=40
        )
        
        # Create ImageClip from the text image
        txt_clip = ImageClip(text_img, duration=sub.end.seconds - sub.start.seconds)
        txt_clip = txt_clip.set_start(sub.start.seconds).set_position(('center', 'bottom'))
        txt_clips.append(txt_clip)
    
    # Composite the video and text clips
    final = CompositeVideoClip([video, *txt_clips])
    
    # Add back the original audio
    final = final.set_audio(video.audio)
    
    final.write_videofile(output_path, codec='libx264', fps=video.fps, audio_codec='aac')
