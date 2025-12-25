import gradio as gr
import subprocess
import os
import json
import tempfile
import re
import shutil
from pathlib import Path

# Create temp directory
TEMP_DIR = tempfile.mkdtemp()
OUTPUT_DIR = os.path.join(TEMP_DIR, "downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def search_youtube(query, max_results=15):
    """Search YouTube and return video list"""
    try:
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--skip-download',
            '--no-warnings',
            '--quiet',
            f'ytsearch{max_results}:{query}'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            return None, "❌ Search failed. Try a different query."
        
        videos = []
        lines = result.stdout.strip().split('\n')
        
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                videos.append({
                    'title': data.get('title', 'No title')[:100],
                    'url': data.get('webpage_url', ''),
                    'duration': data.get('duration', 0),
                    'view_count': data.get('view_count', 0),
                    'thumbnail': data.get('thumbnail', ''),
                    'uploader': data.get('uploader', 'Unknown')[:50],
                    'id': data.get('id', '')
                })
            except json.JSONDecodeError:
                continue
        
        if not videos:
            return None, "❌ No results found."
        
        return videos, f"✅ Found {len(videos)} videos"
        
    except subprocess.TimeoutExpired:
        return None, "❌ Search timed out. Try again."
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

def format_duration(seconds):
    """Convert seconds to MM:SS format"""
    if not seconds:
        return "Unknown"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"

def format_views(count):
    """Format view count"""
    if not count:
        return "Unknown"
    if count >= 1000000:
        return f"{count/1000000:.1f}M"
    elif count >= 1000:
        return f"{count/1000:.1f}K"
    return str(count)

def parse_timestamp(timestamp_str):
    """Convert MM:SS to seconds"""
    try:
        parts = timestamp_str.strip().split(':')
        if len(parts) == 2:
            mins, secs = int(parts[0]), int(parts[1])
            return mins * 60 + secs
        return None
    except:
        return None

def parse_timestamps(text):
    """Parse multiple timestamp ranges"""
    lines = text.strip().split('\n')
    clips = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        match = re.match(r'(\d+:\d+)\s*-\s*(\d+:\d+)', line)
        if match:
            start_str, end_str = match.groups()
            start_sec = parse_timestamp(start_str)
            end_sec = parse_timestamp(end_str)
            
            if start_sec is not None and end_sec is not None and start_sec < end_sec:
                clips.append({
                    'start': start_str,
                    'end': end_str,
                    'start_sec': start_sec,
                    'end_sec': end_sec
                })
    
    return clips

def download_clip(video_url, start_time, end_time, output_name, quality, crop_vertical):
    """Download a specific clip from video"""
    try:
        output_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        
        # Base command
        cmd = [
            'yt-dlp',
            video_url,
            '--download-sections', f'*{start_time}-{end_time}',
            '-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
            '--merge-output-format', 'mp4',
            '-o', output_path,
            '--no-warnings',
            '--quiet'
        ]
        
        # Add crop if requested
        if crop_vertical:
            cmd.extend([
                '--postprocessor-args',
                'ffmpeg:-vf scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
            ])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path, "✅ Downloaded"
        else:
            return None, "❌ Failed"
            
    except subprocess.TimeoutExpired:
        return None, "❌ Timeout"
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

# Global state
search_results = []
selected_video = None

def perform_search(query):
    """Search and display results"""
    global search_results
    
    if not query or query.strip() == "":
        return (
            "❌ Please enter a search query",
            gr.update(visible=True, value=""),
            gr.update(visible=False),
            []
        )
    
    videos, msg = search_youtube(query.strip())
    
    if videos is None:
        return (
            msg,
            gr.update(visible=True, value=""),
            gr.update(visible=False),
            []
        )
    
    search_results = videos
    
    # Create results display
    results_data = []
    for i, video in enumerate(videos):
        duration = format_duration(video['duration'])
        views = format_views(video['view_count'])
        results_data.append([
            i,
            video['title'],
            views,
            duration,
            video['uploader']
        ])
    
    return (
        msg,
        gr.update(visible=False),
        gr.update(visible=True),
        results_data
    )

def select_video_handler(evt: gr.SelectData):
    """Handle video selection from table"""
    global selected_video, search_results
    
    try:
        index = evt.index[0]  # Get row index
        if 0 <= index < len(search_results):
            selected_video = search_results[index]
            
            info = f"""### 📹 Selected Video

**{selected_video['title']}**

- **Duration:** {format_duration(selected_video['duration'])}
- **Views:** {format_views(selected_video['view_count'])}
- **Uploader:** {selected_video['uploader']}
- **Watch:** [{selected_video['url']}]({selected_video['url']})

---

### ✂️ Enter Your Timestamps Below
Format: `2:30-3:15` (one per line)
"""
            
            return (
                info,
                gr.update(visible=False),
                gr.update(visible=True),
                ""
            )
    except Exception as e:
        print(f"Selection error: {e}")
    
    return "❌ Selection failed", gr.update(visible=True), gr.update(visible=False), ""

def process_download(timestamps_text, clip_name_prefix, quality, crop_vertical):
    """Process and download all clips"""
    global selected_video
    
    if selected_video is None:
        return "❌ No video selected", []
    
    if not timestamps_text or timestamps_text.strip() == "":
        return "❌ Please enter timestamps", []
    
    if not clip_name_prefix or clip_name_prefix.strip() == "":
        clip_name_prefix = "clip"
    
    # Parse timestamps
    clips = parse_timestamps(timestamps_text)
    
    if not clips:
        return "❌ No valid timestamps. Use format: 2:30-3:15 (one per line)", []
    
    # Download each clip
    status_lines = [f"🎬 Processing {len(clips)} clips from:\n{selected_video['title']}\n"]
    downloaded_files = []
    
    for i, clip in enumerate(clips, 1):
        clip_filename = f"{clip_name_prefix}_{i}"
        status_lines.append(f"\n⏳ Clip {i}/{len(clips)}: {clip['start']}-{clip['end']}...")
        
        file_path, msg = download_clip(
            selected_video['url'],
            clip['start'],
            clip['end'],
            clip_filename,
            quality,
            crop_vertical
        )
        
        status_lines.append(f"   {msg}")
        
        if file_path and os.path.exists(file_path):
            downloaded_files.append(file_path)
    
    status_lines.append(f"\n\n✅ Successfully downloaded {len(downloaded_files)}/{len(clips)} clips!")
    status_lines.append(f"\n💾 Download files immediately - they will be deleted when session ends.")
    
    return "\n".join(status_lines), downloaded_files

def go_back_to_search():
    """Return to search results"""
    return gr.update(visible=True), gr.update(visible=False)

# Gradio Interface
with gr.Blocks(title="YouTube Clip Finder", theme=gr.themes.Soft()) as app:
    
    gr.Markdown("""
    # 🎬 YouTube Clip Finder & Downloader
    ### Search YouTube → Select Video → Enter Timestamps → Download Clips
    """)
    
    with gr.Column(visible=True) as search_page:
        gr.Markdown("### 🔍 Search YouTube")
        
        search_input = gr.Textbox(
            label="Search Query",
            placeholder="foreigners react to Indian street food",
            lines=1
        )
        
        search_btn = gr.Button("🔎 SEARCH YOUTUBE", variant="primary", size="lg")
        search_status = gr.Textbox(label="Status", interactive=False, lines=2)
        
        results_table = gr.Dataframe(
            headers=["#", "Title", "Views", "Duration", "Uploader"],
            datatype=["number", "str", "str", "str", "str"],
            label="📺 Results (Click a row to select)",
            interactive=False,
            wrap=True,
            visible=False
        )
    
    with gr.Column(visible=False) as video_page:
        back_btn = gr.Button("⬅️ BACK TO SEARCH RESULTS", variant="secondary")
        
        video_info = gr.Markdown("### Video Details")
        
        gr.Markdown("---")
        
        timestamps_input = gr.Textbox(
            label="✂️ Timestamps (one per line)",
            placeholder="2:30-3:15\n5:40-6:20\n8:10-8:45",
            lines=5
        )
        
        with gr.Row():
            clip_name = gr.Textbox(
                label="Clip Name Prefix",
                value="clip",
                placeholder="my_video"
            )
            quality_select = gr.Dropdown(
                choices=["1080", "720", "480"],
                value="720",
                label="Quality"
            )
        
        crop_checkbox = gr.Checkbox(label="✅ Crop to 9:16 Vertical", value=False)
        
        download_btn = gr.Button("📥 DOWNLOAD CLIPS", variant="primary", size="lg")
        
        download_status = gr.Textbox(label="Download Status", lines=8, interactive=False)
        download_files = gr.File(label="📦 Downloaded Clips (Download Now!)", file_count="multiple")
    
    # Event handlers
    search_btn.click(
        fn=perform_search,
        inputs=[search_input],
        outputs=[search_status, search_page, results_table, results_table]
    )
    
    results_table.select(
        fn=select_video_handler,
        outputs=[video_info, search_page, video_page, download_status]
    )
    
    back_btn.click(
        fn=go_back_to_search,
        outputs=[search_page, video_page]
    )
    
    download_btn.click(
        fn=process_download,
        inputs=[timestamps_input, clip_name, quality_select, crop_checkbox],
        outputs=[download_status, download_files]
    )
    
    gr.Markdown("""
    ---
    ### 💡 Tips:
    - **Timestamp format:** Use `2:30-3:15` (minutes:seconds)
    - **Multiple clips:** Enter one per line
    - **Quality:** 720p recommended (good balance)
    - **Vertical crop:** Enable for TikTok/Instagram Reels/YouTube Shorts
    - **Download immediately:** Files are temporary and deleted when session ends
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False
    )
