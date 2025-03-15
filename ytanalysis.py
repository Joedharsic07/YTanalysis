from youtube_transcript_api import YouTubeTranscriptApi
import streamlit as st
import google.generativeai as genai
import re
import json
import os
from dotenv import load_dotenv  

# Load API Key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("❌ API key missing! Set GEMINI_API_KEY in environment variables.")
    st.stop()

# Initialize Gemini Model
genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

# Transcript storage directory
TRANSCRIPT_DIR = "cached_transcripts"
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

# Function to extract video ID from URL
def extract_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None

# Convert timestamp from seconds to MM:SS
def format_time(seconds):
    try:
        seconds = float(seconds)
        minutes = int(seconds) // 60
        sec = int(seconds) % 60
        return f"{minutes:02}:{sec:02}"
    except ValueError:
        return "N/A"

# Save transcript to a file
def save_transcript(video_id, transcript):
    file_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

# Load transcript from a file
def load_transcript(video_id):
    file_path = os.path.join(TRANSCRIPT_DIR, f"{video_id}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

# Get transcript with caching
def get_transcript(video_id):
    cached_transcript = load_transcript(video_id)
    if cached_transcript:
        return cached_transcript, None

    try:
        transcript_data = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = [{"start": entry["start"], "text": entry["text"]} for entry in transcript_data]
        save_transcript(video_id, transcript)  # Save for future use
        return transcript, None
    except Exception as e:
        return None, f"Error: {str(e)}"

# Analyze ad quality using Gemini
def analyze_ad_quality(transcript):
    if not transcript:
        st.error("⚠️ No transcript available for analysis.")
        return None

    transcript_formatted = "\n".join(
        f"[{format_time(entry['start'])}] {entry['text']}" for entry in transcript
    )

    prompt = f"""
    You are an expert in analyzing YouTube ad integrations.

    **Extract the Ad Segment and Evaluate its Quality**:
    - Identify the **ad start & end timestamps** (MM:SS format).
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
      "start_time": "MM:SS",
      "end_time": "MM:SS",
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
        response = model.generate_content(prompt)
        clean_text = response.text.strip().strip("```json").strip("```").strip()
        ad_data = json.loads(clean_text)

        if "start_time" in ad_data and isinstance(ad_data["start_time"], (int, float)):
            ad_data["start_time"] = format_time(ad_data["start_time"])
        if "end_time" in ad_data and isinstance(ad_data["end_time"], (int, float)):
            ad_data["end_time"] = format_time(ad_data["end_time"])

        return ad_data
    except json.JSONDecodeError as e:
        st.error(f"⚠️ JSON Parsing Error: {e} - LLM Response: {response.text}")
        return None
    except Exception as e:
        st.error(f"LLM Error: {e}")
        return None


# Streamlit UI
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
            
            st.markdown(f"## 🎥 Video: [{video_url}](https://www.youtube.com/watch?v={video_id})")

            with st.spinner("Fetching transcript..."):
                transcript, error = get_transcript(video_id)

            if error:
                st.error(error)
                continue

            with st.spinner("Analyzing ad quality..."):
                analysis = analyze_ad_quality(transcript)

            if analysis:
                st.markdown(f"### **📢 Ad Details**")
                st.markdown(f"**🔹 Product Name:** {analysis['product_name']}")
                st.markdown(f"**⏳ Ad Time Range:** {analysis['start_time']} - {analysis['end_time']}")

                st.markdown(f"### **⭐ Overall Ad Score: {analysis['overall_score']}/10**")
                st.markdown(f"📌 {analysis['overall_summary']}")

                # Ad Metrics Section
                st.markdown(f"### **📊 Ad Quality Metrics:**")
                
                metrics = [
                    ("Ad Naturalness", "ad_naturalness"),
                    ("Persuasiveness", "persuasiveness"),
                    ("Trustworthiness", "trustworthiness"),
                    ("Ad Length & Placement", "ad_length_placement"),
                    ("Engagement", "engagement"),
                ]

                for title, key in metrics:
                    st.markdown(f"**🔹 {title}:** {analysis[key]['score']}/10")
                    st.markdown(f"   - {analysis[key]['explanation']}")

                st.markdown("---")  
            else:
                st.warning(f"No advertisement found in {video_url}.")
    else:
        st.warning("Please enter at least one valid YouTube link.")
