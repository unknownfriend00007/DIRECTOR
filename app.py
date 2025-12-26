import gradio as gr
import os
import tempfile
import re
import logging
import subprocess
from datetime import datetime

# Setup comprehensive logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create temp directory
TEMP_DIR = tempfile.mkdtemp()
OUTPUT_DIR = os.path.join(TEMP_DIR, "downloads")
os.makedirs(OUTPUT_DIR, exist_ok=True)

logger.info(f"Temp directory created: {TEMP_DIR}")
logger.info(f"Output directory: {OUTPUT_DIR}")

def search_youtube(query, max_results=15):
    """Search YouTube using yt_dlp Python API"""
    logger.info(f"=== SEARCH STARTED ===")
    logger.info(f"Query: {query}")
    
    try:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
        }
        
        logger.info(f"Search options: {ydl_opts}")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        
        if not search_result or 'entries' not in search_result:
            logger.warning("No results found in search")
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
        
        logger.info(f"Found {len(videos)} videos")
        
        if not videos:
            return None, "❌ No valid results found."
        
        return videos, f"✅ Found {len(videos)} videos"
        
    except Exception as e:
        logger.error(f"Search error: {str(e)}", exc_info=True)
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
    logger.info(f"=== PARSING TIMESTAMPS ===")
    logger.info(f"Raw input: {text}")
    
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
            
            logger.info(f"Parsed: {start_str} ({start_sec}s) - {end_str} ({end_sec}s)")
            
            if start_sec is not None and end_sec is not None and start_sec < end_sec:
                clips.append({
                    'start': start_str,
                    'end': end_str,
                    'start_sec': start_sec,
                    'end_sec': end_sec
                })
    
    logger.info(f"Total clips parsed: {len(clips)}")
    return clips

def download_clip_ultrafast(video_url, start_time, end_time, output_name, quality, crop_vertical):
    """
    ULTRA FAST METHOD: Stream copy only
    - Downloads segment with yt-dlp
    - Trims with FFmpeg stream copy (no re-encoding)
    - 10-15x faster but ±1-2 second accuracy
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== ULTRA FAST DOWNLOAD STARTED ===")
    logger.info(f"{'='*80}")
    logger.info(f"Video URL: {video_url}")
    logger.info(f"Start: {start_time}s, End: {end_time}s, Duration: {end_time - start_time}s")
    
    try:
        import yt_dlp
        
        # Download larger segment with stream copy
        padding = 10
        padded_start = max(0, start_time - padding)
        padded_end = end_time + padding
        
        temp_path = os.path.join(OUTPUT_DIR, f"temp_{output_name}.mp4")
        final_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        
        logger.info(f"⚡⚡ STEP 1: Fast download {padded_start}s-{padded_end}s")
        
        ydl_opts = {
            'format': f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': temp_path,
            'download_ranges': yt_dlp.utils.download_range_func(None, [(padded_start, padded_end)]),
            'force_keyframes_at_cuts': True,
            'postprocessor_args': ['-c', 'copy'],
            'quiet': True,
        }
        
        # Add cookies
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        if not os.path.exists(temp_path):
            raise Exception("Download failed")
        
        logger.info(f"✅ Downloaded: {os.path.getsize(temp_path)} bytes")
        
        # Step 2: Stream copy trim (FAST - no re-encoding)
        logger.info(f"⚡⚡ STEP 2: Stream copy trim (no re-encode)")
        
        trim_start = start_time - padded_start
        trim_duration = end_time - start_time
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(trim_start),
            '-i', temp_path,
            '-t', str(trim_duration),
            '-c', 'copy',  # PURE STREAM COPY!
            '-avoid_negative_ts', 'make_zero',
            '-y',
            final_path
        ]
        
        if crop_vertical:
            logger.warning("⚠️ Crop not available in Ultra Fast mode (requires re-encoding)")
        
        logger.info(f"Running: {' '.join(ffmpeg_cmd[:10])}...")
        
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr[:300]}")
            raise Exception(f"FFmpeg failed: {result.stderr[:150]}")
        
        # Clean up
        os.remove(temp_path)
        
        if os.path.exists(final_path):
            file_size = os.path.getsize(final_path)
            logger.info(f"✅ ULTRA FAST SUCCESS: {file_size} bytes")
            return final_path, f"✅ Downloaded (Ultra Fast, {file_size // 1024}KB)"
        
        raise Exception("Output file not created")
        
    except Exception as e:
        logger.error(f"❌ Ultra fast failed: {str(e)}", exc_info=True)
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return None, f"❌ Error: {str(e)}"

def download_clip_hybrid(video_url, start_time, end_time, output_name, quality, crop_vertical):
    """
    TRUE HYBRID METHOD: Fast download + precise re-encode
    - Downloads segment with yt-dlp (any format, fast)
    - Re-encodes ONLY the exact clip with FFmpeg
    - 3-5x faster than full yt-dlp re-encode
    - 100% accurate timestamps
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== TRUE HYBRID DOWNLOAD STARTED ===")
    logger.info(f"{'='*80}")
    logger.info(f"Video URL: {video_url}")
    logger.info(f"Start: {start_time}s, End: {end_time}s, Duration: {end_time - start_time}s")
    
    try:
        import yt_dlp
        
        # Step 1: Download larger segment (any method, doesn't matter)
        padding = 10
        padded_start = max(0, start_time - padding)
        padded_end = end_time + padding
        
        temp_path = os.path.join(OUTPUT_DIR, f"temp_{output_name}.mp4")
        final_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        
        logger.info(f"⚡ STEP 1: Downloading segment {padded_start}s-{padded_end}s")
        
        ydl_opts = {
            'format': f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': temp_path,
            'download_ranges': yt_dlp.utils.download_range_func(None, [(padded_start, padded_end)]),
            'force_keyframes_at_cuts': True,
            'postprocessor_args': ['-c', 'copy'],  # Try stream copy for speed
            'quiet': True,
        }
        
        # Add cookies
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        
        if not os.path.exists(temp_path):
            raise Exception("Download failed")
        
        temp_size = os.path.getsize(temp_path)
        logger.info(f"✅ Downloaded: {temp_size} bytes")
        
        # Step 2: Precise re-encode of ONLY the target clip
        logger.info(f"🎯 STEP 2: Re-encoding exact clip with FFmpeg")
        
        trim_start = start_time - padded_start
        trim_duration = end_time - start_time
        
        logger.info(f"Trimming: start={trim_start}s, duration={trim_duration}s")
        
        # Build FFmpeg command for precise re-encode
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(trim_start),        # Input seeking (fast)
            '-i', temp_path,
            '-t', str(trim_duration),      # Exact duration
            '-c:v', 'libx264',             # Re-encode video
            '-preset', 'ultrafast',        # Fastest preset
            '-crf', '23',                  # Good quality
            '-c:a', 'aac',                 # Re-encode audio
            '-b:a', '128k',
        ]
        
        # Add crop if requested
        if crop_vertical:
            logger.info("Adding 9:16 vertical crop")
            ffmpeg_cmd.extend([
                '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920'
            ])
        
        ffmpeg_cmd.extend([
            '-avoid_negative_ts', 'make_zero',
            '-y',
            final_path
        ])
        
        logger.info(f"Running FFmpeg: {' '.join(ffmpeg_cmd[:12])}...")
        
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg stderr: {result.stderr[:500]}")
            raise Exception(f"FFmpeg failed: {result.stderr[:200]}")
        
        # Clean up temp file
        os.remove(temp_path)
        logger.info("Temp file cleaned")
        
        if os.path.exists(final_path):
            file_size = os.path.getsize(final_path)
            logger.info(f"✅ HYBRID SUCCESS: {file_size} bytes")
            return final_path, f"✅ Downloaded (Hybrid, {file_size // 1024}KB)"
        
        raise Exception("Output file not created")
        
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout")
        return None, "❌ Timeout - try shorter clip or Ultra Fast mode"
        
    except Exception as e:
        logger.error(f"❌ Hybrid failed: {str(e)}", exc_info=True)
        if 'temp_path' in locals() and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return None, f"❌ Error: {str(e)}"

def download_clip_accurate(video_url, start_time, end_time, output_name, quality, crop_vertical):
    """
    ACCURATE METHOD: Full yt-dlp re-encode (original method)
    - Direct download with yt-dlp handling everything
    - Exact timestamps guaranteed
    - Slowest but most reliable
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== ACCURATE DOWNLOAD STARTED ===")
    logger.info(f"{'='*80}")
    logger.info(f"Video URL: {video_url}")
    logger.info(f"Start: {start_time}s, End: {end_time}s, Duration: {end_time - start_time}s")
    
    try:
        import yt_dlp
        
        output_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        logger.info(f"Output path: {output_path}")
        
        ydl_opts = {
            'format': f'best[height<={quality}]/best',
            'outtmpl': output_path,
            'verbose': True,
            'no_warnings': False,
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_time, end_time)]),
            'force_keyframes_at_cuts': True,
        }
        
        # Add cookies
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            logger.info("Using cookies from environment")
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        # Add crop if requested
        if crop_vertical:
            logger.info("Adding vertical crop filter")
            ydl_opts['postprocessor_args'] = {
                'ffmpeg': ['-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920']
            }
        
        logger.info("Starting download...")
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            logger.info(f"Video title: {info.get('title', 'Unknown')}")
        
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ ACCURATE SUCCESS: {output_path} ({file_size} bytes)")
            return output_path, f"✅ Downloaded (Accurate, {file_size // 1024}KB)"
        
        # Check for similar files
        all_files = os.listdir(OUTPUT_DIR)
        for filename in all_files:
            if output_name in filename and filename.endswith('.mp4'):
                full_path = os.path.join(OUTPUT_DIR, filename)
                file_size = os.path.getsize(full_path)
                logger.info(f"✅ Found: {filename} ({file_size} bytes)")
                return full_path, f"✅ Downloaded as {filename} ({file_size // 1024}KB)"
        
        raise Exception("No output file created")
            
    except Exception as e:
        logger.error(f"❌ Accurate download failed: {str(e)}", exc_info=True)
        return None, f"❌ Error: {str(e)}"

def download_clip(video_url, start_time, end_time, output_name, quality, crop_vertical, processing_mode):
    """
    Universal download function - routes to correct method
    """
    if "Ultra Fast" in processing_mode:
        return download_clip_ultrafast(video_url, start_time, end_time, output_name, quality, crop_vertical)
    elif "Hybrid" in processing_mode:
        return download_clip_hybrid(video_url, start_time, end_time, output_name, quality, crop_vertical)
    else:  # Full Re-encode
        return download_clip_accurate(video_url, start_time, end_time, output_name, quality, crop_vertical)

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
    
    logger.info(f"=== VIDEO SELECTED ===")
    
    try:
        index = evt.index[0]
        logger.info(f"Selected index: {index}")
        
        if 0 <= index < len(search_results):
            selected_video = search_results[index]
            
            video_id = selected_video.get('id', '')
            full_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else selected_video.get('url', '')
            selected_video['url'] = full_url
            
            logger.info(f"Selected video: {selected_video['title']}")
            logger.info(f"Video URL: {full_url}")
            
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
        logger.error(f"Selection error: {e}", exc_info=True)
    
    return "❌ Selection failed", gr.update(visible=True), gr.update(visible=False), ""

def process_download(timestamps_text, clip_name_prefix, quality, crop_vertical, processing_mode):
    """Process and download all clips"""
    global selected_video
    
    logger.info(f"\n{'='*80}")
    logger.info(f"=== PROCESSING DOWNLOAD REQUEST ===")
    logger.info(f"{'='*80}")
    
    if selected_video is None:
        logger.warning("No video selected")
        return "❌ No video selected", []
    
    logger.info(f"Video: {selected_video['title']}")
    logger.info(f"URL: {selected_video['url']}")
    logger.info(f"Processing mode: {processing_mode}")
    
    if not timestamps_text or timestamps_text.strip() == "":
        logger.warning("No timestamps provided")
        return "❌ Please enter timestamps", []
    
    if not clip_name_prefix or clip_name_prefix.strip() == "":
        clip_name_prefix = "clip"
    
    logger.info(f"Clip name prefix: {clip_name_prefix}")
    logger.info(f"Quality: {quality}")
    logger.info(f"Crop vertical: {crop_vertical}")
    
    clips = parse_timestamps(timestamps_text)
    
    if not clips:
        logger.warning("No valid timestamps parsed")
        return "❌ No valid timestamps. Use format: 2:30-3:15 (one per line)", []
    
    # Set emoji based on mode
    if "Ultra Fast" in processing_mode:
        mode_emoji = "⚡⚡"
    elif "Hybrid" in processing_mode:
        mode_emoji = "⚡"
    else:
        mode_emoji = "🎯"
    
    status_lines = [f"{mode_emoji} Processing {len(clips)} clips using {processing_mode}"]
    status_lines.append(f"📹 Video: {selected_video['title']}\n")
    downloaded_files = []
    
    for i, clip in enumerate(clips, 1):
        clip_filename = f"{clip_name_prefix}_{i}"
        status_lines.append(f"\n⏳ Clip {i}/{len(clips)}: {clip['start']}-{clip['end']}...")
        
        logger.info(f"\n--- Processing clip {i}/{len(clips)} ---")
        
        file_path, msg = download_clip(
            selected_video['url'],
            clip['start_sec'],
            clip['end_sec'],
            clip_filename,
            quality,
            crop_vertical,
            processing_mode
        )
        
        status_lines.append(f"   {msg}")
        
        if file_path and os.path.exists(file_path):
            downloaded_files.append(file_path)
            logger.info(f"✅ Clip {i} successful: {file_path}")
        else:
            logger.error(f"❌ Clip {i} failed")
    
    status_lines.append(f"\n\n✅ Successfully downloaded {len(downloaded_files)}/{len(clips)} clips!")
    status_lines.append(f"\n💾 Download files immediately - they will be deleted when session ends.")
    
    logger.info(f"=== DOWNLOAD COMPLETE: {len(downloaded_files)}/{len(clips)} successful ===")
    
    return "\n".join(status_lines), downloaded_files

def go_back_to_search():
    """Return to search results"""
    return gr.update(visible=True), gr.update(visible=False)

# Gradio Interface
with gr.Blocks(title="YouTube Clip Finder", theme=gr.themes.Soft()) as app:
    
    gr.Markdown("""
    # 🎬 YouTube Clip Finder & Downloader
    ### Search YouTube → Select Video → Enter Timestamps → Download Clips
    
    ⚠️ **All activity is logged to Render logs for debugging**
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
        
        # THREE PROCESSING MODES
        processing_mode = gr.Radio(
            choices=[
                "⚡⚡ Ultra Fast (30-60 sec, ±1-2s accuracy)",
                "⚡ Hybrid (1-2 min, exact timestamps) - RECOMMENDED",
                "🎯 Full Re-encode (5+ min, exact, slower)"
            ],
            value="⚡ Hybrid (1-2 min, exact timestamps) - RECOMMENDED",
            label="Processing Mode",
            info="Ultra Fast: Stream copy only | Hybrid: Fast download + precise FFmpeg trim | Full: yt-dlp handles everything"
        )
        
        crop_checkbox = gr.Checkbox(
            label="✅ Crop to 9:16 Vertical (Not available in Ultra Fast mode)", 
            value=False
        )
        
        download_btn = gr.Button("📥 DOWNLOAD CLIPS", variant="primary", size="lg")
        
        download_status = gr.Textbox(label="Download Status", lines=10, interactive=False)
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
        inputs=[timestamps_input, clip_name, quality_select, crop_checkbox, processing_mode],
        outputs=[download_status, download_files]
    )
    
    gr.Markdown("""
    ---
    ### 💡 Tips:
    - **Timestamp format:** Use `2:30-3:15` (minutes:seconds)
    - **Multiple clips:** Enter one per line
    - **Quality:** 720p recommended (good balance)
    - **Processing Mode:**
      - **⚡⚡ Ultra Fast:** 30-60 seconds, stream copy only, ±1-2 second accuracy, no crop support
      - **⚡ Hybrid (RECOMMENDED):** 1-2 minutes, exact timestamps, supports crop, best balance
      - **🎯 Full Re-encode:** 5+ minutes, exact timestamps, most reliable but slowest
    - **Vertical crop:** Enable for TikTok/Instagram Reels/YouTube Shorts (not in Ultra Fast mode)
    - **Check Render logs** if downloads fail (Dashboard → Logs tab)
    - **MADE BY Raghav
    
    ### 📊 Mode Comparison:
    | Feature | Ultra Fast ⚡⚡ | Hybrid ⚡ (RECOMMENDED) | Full Re-encode 🎯 |
    |---------|---------------|------------------------|-------------------|
    | **Speed** | 30-60 sec | 1-2 min | 5+ min |
    | **Accuracy** | ±1-2 sec | Exact | Exact |
    | **Quality** | Original | High | High |
    | **Crop Support** | ❌ No | ✅ Yes | ✅ Yes |
    | **Best for** | Quick previews | Most use cases | Maximum reliability |
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting app on port {port}")
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False
    )
