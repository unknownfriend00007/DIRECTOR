import gradio as gr
import os
import tempfile
import re

# Create temp directory
TEMP_DIR = tempfile.mkdtemp()
OUTPUT_DIR = os.path.join(TEMP_DIR, "downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def search_youtube(query, max_results=15):
    """Search YouTube using yt_dlp Python API with cookies"""
    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
        }
        
        # Add cookies from environment variable
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        
        if not search_result or 'entries' not in search_result:
            return None, "❌ No results found."
        
        videos = []
        for entry in search_result['entries']:
            if entry:
                videos.append({
                    'title': entry.get('title', 'No title')[:100],
                    'url': entry.get('url', ''),
                    'duration': entry.get('duration', 0),
                    'view_count': entry.get('view_count', 0),
                    'thumbnail': entry.get('thumbnail', ''),
                    'uploader': entry.get('uploader', 'Unknown')[:50],
                    'id': entry.get('id', '')
                })
        
        if not videos:
            return None, "❌ No valid results found."
        
        return videos, f"✅ Found {len(videos)} videos"
        
    except Exception as e:
        return None, f"❌ Search error: {str(e)[:200]}"

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
    """Download a specific clip using yt_dlp Python API with cookies"""
    try:
        import yt_dlp
        
        output_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        
        # Build options
        ydl_opts = {
            'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]),
        }
        
        # Add cookies from environment variable
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        # Add crop postprocessing if requested
        if crop_vertical:
            ydl_opts['postprocessor_args'] = {
                'ffmpeg': ['-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920']
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        if os.path.exists(output_path):
            return output_path, "✅ Downloaded"
        else:
            return None, "❌ Failed - file not created"
            
    except Exception as e:
        return None, f"❌ Error: {str(e)[:100]}"

# Global state
search_results = []
selected_video = None

def perform_search(query):
    """Search and display results"""
    global search_results
    
    if not query or query.strip() == "":
        return "❌ Please enter a search query", gr.update(visible=False, value=[])
    
    videos, msg = search_youtube(query.strip())
    
    if videos is None:
        return msg, gr.update(visible=False, value=[])
    
    search_results = videos
    
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
    
    return msg, gr.update(visible=True, value=results_data)

def select_video_handler(evt: gr.SelectData):
    """Handle video selection from table"""
    global selected_video, search_results
    
    try:
        index = evt.index[0]
        if 0 <= index < len(search_results):
            selected_video = search_results[index]
            
            video_id = selected_video.get('id', '')
            full_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else selected_video.get('url', '')
            selected_video['url'] = full_url
            
            info = f"""### 📹 Selected Video

**{selected_video['title']}**

- **Duration:** {format_duration(selected_video['duration'])}
- **Views:** {format_views(selected_video['view_count'])}
- **Uploader:** {selected_video['uploader']}
- **Watch:** [Open on YouTube]({full_url})

---

### ✂️ Enter Your Timestamps Below
Format: `2:30-3:15` (one per line)
"""
            
            return info, gr.update(visible=False), gr.update(visible=True), ""
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
    
    clips = parse_timestamps(timestamps_text)
    
    if not clips:
        return "❌ No valid timestamps. Use format: 2:30-3:15 (one per line)", []
    
    status_lines = [f"🎬 Processing {len(clips)} clips from:\n{selected_video['title']}\n"]
    downloaded_files = []
    
    for i, clip in enumerate(clips, 1):
        clip_filename = f"{clip_name_prefix}_{i}"
        status_lines.append(f"\n⏳ Clip {i}/{len(clips)}: {clip['start']}-{clip['end']}...")
        
        file_path, msg = download_clip(
            selected_video['url'],
            clip['start_sec'],  # ✅ FIXED - now using seconds (int)
            clip['end_sec'],    # ✅ FIXED - now using seconds (int)
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
    
    ⚠️ **Setup Required:** Add your YouTube cookies as environment variable `YOUTUBE_COOKIES` to bypass bot detection.
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
        outputs=[search_status, results_table]
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
