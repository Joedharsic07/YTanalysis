from youtube_transcript_api import YouTubeTranscriptApi
import streamlit as st
import google.generativeai as genai
import re
import json
import os
import requests
from dotenv import load_dotenv  

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
youtube_api_key = os.getenv("YOUTUBE_API_KEY")

if not api_key:
    st.error("❌ GEMINI API key missing! Set GEMINI_API_KEY in environment variables.")
    st.stop()

if not youtube_api_key:
    st.error("❌ YouTube API key missing! Set YOUTUBE_API_KEY in environment variables.")
    st.stop()

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

TRANSCRIPT_DIR = "cached_transcripts"
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

def extract_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def format_time(seconds):
    try:
        seconds = float(seconds)
        
        hours = int(seconds) // 3600
        minutes = (int(seconds) % 3600) // 60
        secs = int(seconds) % 60
        
        if hours > 0:
            return f"{hours:01}:{minutes:02}:{secs:02}"
        else:
            return f"{minutes:02}:{secs:02}"
    except (ValueError, TypeError):
        return "N/A"

def get_video_details(video_id):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={youtube_api_key}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            snippet = data["items"][0]["snippet"]
            return snippet["title"], snippet["channelTitle"]
    return "Unknown Title", "Unknown Channel"

def save_transcript(video_id, transcript):
    file_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

def load_transcript(video_id):
    file_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def get_transcript(video_id):
    cached_transcript = load_transcript(video_id)
    if cached_transcript:
        return cached_transcript, None

    try:
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = [{"start": entry["start"], "text": entry["text"]} for entry in transcript_data]
        save_transcript(video_id, transcript) 
        return transcript, None
    except Exception as e:
        return None, f"Error: {str(e)}"

def analyze_ad_quality(transcript, video_id):
    if not transcript:
        st.error("⚠️ No transcript available for analysis.")
        return None
    if transcript:
        last_entry = transcript[-1]
        if 'start' in last_entry:
            try:
                last_timestamp = float(last_entry['start'])
                video_length = last_timestamp + 5
            except (ValueError, TypeError):
                video_length = "unknown"
        else:
            video_length = "unknown"
    else:
        video_length = "unknown"

    transcript_formatted = "\n".join(
        f"[{format_time(entry['start'])}] {entry['text']}" for entry in transcript
    )

    prompt = f"""
    You are an expert in analyzing YouTube ad integrations in videos of all lengths.

    **Video Info:**
    - Video ID: {video_id}
    - Estimated video length: {format_time(video_length) if video_length != "unknown" else "unknown"}
    
    **Extract the Ad Segment and Evaluate its Quality**:
    - Carefully analyze the entire transcript to find where the creator is advertising a product or service.
    - Identify the **exact ad start & end timestamps** (in the format shown in the transcript).
    - Make sure your timestamps are accurate for this possibly hour-length video.
    - Detect the **product name** being advertised.
    - Provide a **single Overall Ad Score (1-10)** with a **one-line explanation**.
    - Evaluate the ad using **five key metrics** with **scores (1-10) + short explanations**:
      1. **Ad Naturalness**
      2. **Persuasiveness**
      3. **Trustworthiness**
      4. **Ad Length & Placement**
      5. **Engagement**

    **Transcript:**
    ```
    {transcript_formatted}
    ```

    **Output (JSON Format)**:
    {{
      "product_name": "Detected Product",
      "start_time": "HH:MM:SS or MM:SS format matching transcript",
      "end_time": "HH:MM:SS or MM:SS format matching transcript",
      "overall_score": 0-10,
      "overall_summary": "One-line summary for overall score",
      "ad_naturalness": {{"score": 0-10, "explanation": "1-2 line reason"}},
      "persuasiveness": {{"score": 0-10, "explanation": "1-2 line reason"}},
      "trustworthiness": {{"score": 0-10, "explanation": "1-2 line reason"}},
      "ad_length_placement": {{"score": 0-10, "explanation": "1-2 line reason"}},
      "engagement": {{"score": 0-10, "explanation": "1-2 line reason"}}
    }}
    """

    try:
        response = model.generate_content(prompt, generation_config={"temperature": 0})
        clean_text = response.text.strip().strip("```json").strip("```").strip()
        ad_data = json.loads(clean_text)
        
        return ad_data
    except json.JSONDecodeError as e:
        st.error(f"⚠️ JSON Parsing Error: {e} - LLM Response: {response.text}")
        return None
    except Exception as e:
        st.error(f"LLM Error: {e}")
        return None

st.markdown("<h1 style='text-align: left;'>📊 YouTube Ad Quality Analyzer</h1>", unsafe_allow_html=True)
st.write("Analyze YouTube ad segments for quality and effectiveness.")

video_urls = st.text_area("🔗 Enter YouTube Video Links (One per line)").split("\n")

if st.button("Analyze"):
    valid_videos = [url.strip() for url in video_urls if url.strip()]
    
    if valid_videos:
        for video_url in valid_videos:
            video_id = extract_video_id(video_url)
            if not video_id:
                st.error(f"❌ Invalid YouTube URL: {video_url}")
                continue           
            
            video_title, channel_name = get_video_details(video_id)

            st.markdown(f"### 🎥 Video Title: {video_title}")
            st.markdown(f"""
    <style>
        .youtube-link a {{
            font-size: 20px !important;
            font-weight: bold !important;
            color: #0073e6 !important;
            text-decoration: none !important;
            display: inline-block !important;
            margin-top: 10px !important;
        }}
        .youtube-link a:hover {{
            text-decoration: underline !important;
        }}
    </style>
    <div class="youtube-link">
        <a href="https://www.youtube.com/watch?v={video_id}" target="_blank">{video_url}</a>
    </div>
""", unsafe_allow_html=True)

            st.markdown(f"**📺 Channel Name:** {channel_name}")

            with st.spinner("Fetching transcript..."):
                transcript, error = get_transcript(video_id)

            if error:
                st.error(error)
                continue

            with st.spinner("Analyzing ad quality..."):
                analysis = analyze_ad_quality(transcript, video_id)

            if analysis:
                st.markdown(f"### **📢 Ad Details**")
                st.markdown(f"**🔹 Product Name:** {analysis['product_name']}")
                st.markdown(f"**⏳ Ad Time Range:** {analysis['start_time']} - {analysis['end_time']}")

                st.markdown(f"### **⭐ Overall Ad Score: {analysis['overall_score']}/10**")
                st.markdown(f"📌 {analysis['overall_summary']}")

                st.markdown("### **📊 Ad Quality Metrics:**")
                metrics = [
                    ("Ad Naturalness", "ad_naturalness"),
                    ("Persuasiveness", "persuasiveness"),
                    ("Trustworthiness", "trustworthiness"),
                    ("Ad Length & Placement", "ad_length_placement"),
                    ("Engagement", "engagement"),
                ]
                for idx, (title, key) in enumerate(metrics, start=1):
                    st.markdown(f"**{idx}. {title}: {analysis[key]['score']}/10**")
                    st.markdown(f"   - {analysis[key]['explanation']}")

                st.markdown("---")
    else:
        st.warning("Please enter at least one valid YouTube link.")
