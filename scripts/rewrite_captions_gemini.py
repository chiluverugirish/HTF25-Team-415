import random
import time
from collections import defaultdict
from datetime import datetime
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

FAILED_KEYS_FILE = "disabled_keys.json"
USAGE_FILE = "usage_counts.json"
DAILY_LIMIT = 500
PER_MINUTE_LIMIT = 10
minute_usage_tracker = defaultdict(list)

class GeminiResponse:
    def __init__(self, text):
        self.text = text

# --- Helper functions ---
def load_json_file(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return json.load(f)
    return {}

def save_json_file(filepath, data):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

def load_disabled_keys():
    data = load_json_file(FAILED_KEYS_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    return set(data.get(today, []))

def save_disabled_key(api_key):
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_json_file(FAILED_KEYS_FILE)
    if today not in data: data[today] = []
    if api_key not in data[today]: data[today].append(api_key)
    save_json_file(FAILED_KEYS_FILE, data)

def increment_usage(api_key):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    usage = load_json_file(USAGE_FILE)
    if today not in usage: usage[today] = {}
    if api_key not in usage[today]: usage[today][api_key] = 0
    usage[today][api_key] += 1
    save_json_file(USAGE_FILE, usage)
    # per-minute tracker
    minute = now.strftime("%Y-%m-%d %H:%M")
    minute_usage_tracker[api_key] = [ts for ts in minute_usage_tracker[api_key] if ts.startswith(minute)]
    minute_usage_tracker[api_key].append(now.strftime("%Y-%m-%d %H:%M:%S"))

def has_exceeded_daily_limit(api_key, limit=DAILY_LIMIT):
    today = datetime.now().strftime("%Y-%m-%d")
    usage = load_json_file(USAGE_FILE)
    return usage.get(today, {}).get(api_key, 0) >= limit

def has_exceeded_minute_limit(api_key, limit=PER_MINUTE_LIMIT):
    current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
    recent_times = [ts for ts in minute_usage_tracker[api_key] if ts.startswith(current_minute)]
    return len(recent_times) >= limit

# --- Main function ---

def rewrite_captions(text, style="casual", lang="en", model_name=None, max_retries=10, wait_seconds=5):
    """
    Rewrite captions using multiple Gemini API keys with automatic fallback.
    Polishes text AND translates to target language if needed.
    """
    
    # Language name mapping
    language_names = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "hi": "Hindi",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "ar": "Arabic",
        "ru": "Russian"
    }
    
    target_language = language_names.get(lang.lower(), "English")
    
    # Build the prompt dynamically with translation support
    if lang.lower() == "en":
        # English output - just rewrite with style
        prompt = f"""Rewrite the following text in a {style} style. 
Remove filler words (um, uh, like, you know), fix grammar, and make it clear and engaging.
Only output the rewritten text, nothing else.

Text: '{text}'
"""
    else:
        # Non-English output - translate AND rewrite
        prompt = f"""Translate the following text to {target_language} and rewrite it in a {style} style.
Remove filler words, fix grammar, and make it clear and engaging.
Only output the translated and rewritten text in {target_language}, nothing else.

Text: '{text}'
"""

    print(f"\n{'─'*60}")
    print(f"✨ GEMINI API CALL")
    print(f"{'─'*60}")
    print(f"📝 Input text: {text[:60]}{'...' if len(text) > 60 else ''}")
    print(f"🎨 Style: {style}")
    print(f"🌍 Target Language: {target_language} ({lang})")
    if lang.lower() != "en":
        print(f"🔄 Translation: English → {target_language}")
    print(f"📏 Text length: {len(text)} characters")

    # Load API keys from environment variables
    api_keys = []
    for i in range(1, 29):  # Load keys 1-28
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            api_keys.append(key)
    
    if not api_keys:
        raise RuntimeError("No Gemini API keys found in .env file")

    model_names = [model_name or "gemini-2.5-flash-preview-05-20"]
    disabled_keys_today = load_disabled_keys()

    print(f"🔑 Total API keys: {len(api_keys)}")
    print(f"🚫 Disabled keys today: {len(disabled_keys_today)}")

    for attempt in range(max_retries):
        available_keys = [
            k for k in api_keys
            if k not in disabled_keys_today
            and not has_exceeded_daily_limit(k)
            and not has_exceeded_minute_limit(k)
        ]
        if not available_keys:
            print(f"❌ All API keys disabled or exceeded limits.")
            raise RuntimeError("All API keys disabled or exceeded limits.")

        key = random.choice(available_keys)
        model = random.choice(model_names)

        print(f"\n🔄 Attempt {attempt + 1}/{max_retries}")
        print(f"   🔑 Key: ...{key[-6:]}")
        print(f"   🤖 Model: {model}")
        print(f"   ✅ Available keys: {len(available_keys)}/{len(api_keys)}")

        try:
            import time
            start_time = time.time()
            
            genai.configure(api_key=key)
            gemini = genai.GenerativeModel(model)
            
            response = gemini.generate_content(prompt)
            increment_usage(key)
            
            api_time = time.time() - start_time
            output_text = response.text.strip()
            
            print(f"   ✅ SUCCESS in {api_time:.2f}s")
            print(f"   📤 Output: {output_text[:60]}{'...' if len(output_text) > 60 else ''}")
            print(f"   📊 Output length: {len(output_text)} characters")
            print(f"{'─'*60}")
            
            return GeminiResponse(output_text)
        except Exception as e:
            error_msg = str(e)
            print(f"   ❌ FAILED: {error_msg[:80]}{'...' if len(error_msg) > 80 else ''}")
            save_disabled_key(key)
            if attempt < max_retries - 1:
                print(f"   ⏳ Waiting {wait_seconds}s before retry...")
                time.sleep(wait_seconds)

    print(f"❌ All Gemini API attempts failed after {max_retries} retries.")
    raise RuntimeError("All Gemini API attempts failed after retries.")
