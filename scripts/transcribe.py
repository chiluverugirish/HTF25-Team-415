import ssl
import certifi
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl._create_default_https_context = lambda: ssl_context

from faster_whisper import WhisperModel
import torch
import os

# Cache the model to avoid reloading
_cached_model = None

def transcribe_video(video_path, model_size="base"):
    """
    Transcribe video with optimizations for speed using faster-whisper.
    
    Model sizes (fastest to slowest):
    - tiny: 39M params, ~128x realtime (GPU), lowest accuracy
    - base: 74M params, ~80x realtime (GPU), good accuracy (RECOMMENDED)
    - small: 244M params, ~30x realtime (GPU)
    - medium: 769M params, ~10x realtime (GPU)
    - large-v2: 1550M params, ~4x realtime (GPU)
    - large-v3: 1550M params, ~4x realtime (GPU), best accuracy
    
    faster-whisper is 4-8x faster than OpenAI Whisper!
    """
    global _cached_model
    
    # Use GPU if available (much faster!)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    # Compute type for faster-whisper
    if device == "cuda":
        compute_type = "float16"  # FP16 for GPU (2x faster)
    else:
        compute_type = "int8"  # INT8 for CPU (faster inference)
    
    print("\n" + "="*60)
    print("🎤 WHISPER TRANSCRIPTION STARTED (faster-whisper)")
    print("="*60)
    print(f"📹 Video: {os.path.basename(video_path)}")
    print(f"🧠 Model: {model_size} ({device.upper()})")
    
    # Log GPU info if available
    if device == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"🎮 GPU: {gpu_name} ({gpu_memory:.1f} GB)")
        print(f"⚡ Optimizations: FP16 precision enabled")
        print(f"🚀 Using faster-whisper (4-8x faster)")
    else:
        print(f"⚠️  Running on CPU (slower)")
        print(f"⚡ Optimizations: INT8 quantization enabled")
    
    # Cache model to avoid reloading (saves 5-10 seconds)
    cache_key = f"{model_size}_{device}_{compute_type}"
    if _cached_model is None or _cached_model[0] != cache_key:
        print(f"🔄 Loading {model_size} model...")
        import time
        start_load = time.time()
        
        # Load faster-whisper model
        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=None,  # Use default cache location
            local_files_only=False
        )
        
        _cached_model = (cache_key, model)
        load_time = time.time() - start_load
        print(f"✅ Model loaded in {load_time:.1f}s")
    else:
        print(f"♻️  Using cached {model_size} model (saved ~5-10s)")
        model = _cached_model[1]
    
    # Log transcription parameters
    print(f"\n📋 Transcription Parameters:")
    print(f"   • Language: English (auto-detection disabled)")
    print(f"   • Precision: {compute_type.upper()}")
    print(f"   • VAD Filter: Enabled (removes silence)")
    print(f"   • Beam size: 5 (balanced)")
    
    # Optimized transcription settings
    import time
    start_transcribe = time.time()
    print(f"\n🚀 Starting transcription...")
    
    # faster-whisper transcription
    segments_generator, info = model.transcribe(
        video_path,
        language="en",  # Skip language detection (saves time)
        beam_size=5,
        vad_filter=True,  # Voice activity detection (removes silence)
        vad_parameters=dict(min_silence_duration_ms=500),
        condition_on_previous_text=False,  # Faster processing
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
    )
    
    # Convert generator to list and format as expected
    segments = []
    for segment in segments_generator:
        segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip()
        })
    
    transcribe_time = time.time() - start_transcribe
    segment_count = len(segments)
    
    print(f"✅ Transcription complete in {transcribe_time:.1f}s")
    print(f"📊 Segments found: {segment_count}")
    print(f"📊 Detected language: {info.language} (probability: {info.language_probability:.2%})")
    if segment_count > 0:
        total_duration = segments[-1]['end']
        speed_ratio = total_duration / transcribe_time if transcribe_time > 0 else 0
        print(f"⏱️  Video duration: {total_duration:.1f}s")
        print(f"⚡ Speed: {speed_ratio:.1f}x realtime")
    print("="*60 + "\n")
    
    return segments  # List of segments with start, end, text