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
PREVIEW_DIR = os.path.join(TEMP_DIR, "previews")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PREVIEW_DIR, exist_ok=True)

logger.info(f"Temp directory created: {TEMP_DIR}")
logger.info(f"Output directory: {OUTPUT_DIR}")
logger.info(f"Preview directory: {PREVIEW_DIR}")

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

def generate_preview(video_url, start_time, end_time, preview_name, quality='480'):
    """
    Generate a FAST preview using stream copy
    Returns video path for preview player
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== GENERATING PREVIEW ===")
    logger.info(f"{'='*80}")
    logger.info(f"Video URL: {video_url}")
    logger.info(f"Start: {start_time}s, End: {end_time}s")
    
    try:
        import yt_dlp
        
        preview_path = os.path.join(PREVIEW_DIR, f"{preview_name}_preview.mp4")
        duration = end_time - start_time
        
        # Add 5 second buffer on each side for editing
        buffer_start = max(0, start_time - 5)
        buffer_end = end_time + 5
        buffer_duration = buffer_end - buffer_start
        
        # Get direct video URL
        logger.info(f"⚡ Getting direct video URL...")
        
        ydl_opts = {
            'format': f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        
        # Add cookies
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            direct_url = info['url']
        
        logger.info(f"✅ Got direct URL")
        
        # FFmpeg FAST stream copy with buffer
        logger.info(f"⚡⚡ Generating preview with 5s buffer on each side...")
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(buffer_start),
            '-i', direct_url,
            '-t', str(buffer_duration),
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-y',
            preview_path
        ]
        
        logger.info(f"Running FFmpeg preview...")
        
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr[:500]}")
            raise Exception(f"FFmpeg failed: {result.stderr[:200]}")
        
        logger.info("Preview generated")
        
        if os.path.exists(preview_path):
            file_size = os.path.getsize(preview_path)
            logger.info(f"✅ PREVIEW SUCCESS: {file_size} bytes")
            return preview_path, buffer_start, buffer_end, buffer_duration, "✅ Preview ready"
        
        raise Exception("Preview file not created")
        
    except Exception as e:
        logger.error(f"❌ Preview failed: {str(e)}", exc_info=True)
        return None, 0, 0, 0, f"❌ Preview error: {str(e)[:150]}"

def download_clip_fast(video_url, start_time, end_time, output_name, quality, crop_vertical):
    """
    FAST METHOD: Stream copy (no re-encoding)
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== FAST MODE DOWNLOAD STARTED ===")
    logger.info(f"{'='*80}")
    logger.info(f"Video URL: {video_url}")
    logger.info(f"Start: {start_time}s, End: {end_time}s, Duration: {end_time - start_time}s")
    
    try:
        import yt_dlp
        
        final_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        duration = end_time - start_time
        
        # Get direct video URL
        logger.info(f"⚡ STEP 1: Getting direct video URL...")
        
        ydl_opts = {
            'format': f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        
        # Add cookies
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            direct_url = info['url']
        
        logger.info(f"✅ Got direct URL")
        
        # FFmpeg FAST stream copy
        logger.info(f"⚡⚡ STEP 2: Fast stream copy (no re-encoding)...")
        
        if crop_vertical:
            logger.warning("⚠️ Crop requires re-encoding - switching to precise mode")
            return download_clip_precise(video_url, start_time, end_time, output_name, quality, crop_vertical)
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-i', direct_url,
            '-t', str(duration),
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-y',
            final_path
        ]
        
        logger.info(f"Running FFmpeg stream copy...")
        
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=180
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr[:500]}")
            raise Exception(f"FFmpeg failed: {result.stderr[:200]}")
        
        logger.info("FFmpeg complete")
        
        if os.path.exists(final_path):
            file_size = os.path.getsize(final_path)
            logger.info(f"✅ FAST SUCCESS: {file_size} bytes")
            return final_path, f"✅ Downloaded (Fast, {file_size // 1024}KB, ±2s accuracy)"
        
        raise Exception("Output file not created")
        
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout!")
        return None, "❌ Timeout - clip too long"
        
    except Exception as e:
        logger.error(f"❌ Fast download failed: {str(e)}", exc_info=True)
        return None, f"❌ Error: {str(e)[:150]}"

def download_clip_precise(video_url, start_time, end_time, output_name, quality, crop_vertical):
    """
    PRECISE METHOD: Re-encode for exact timestamps with optimized compression
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== PRECISE MODE DOWNLOAD STARTED ===")
    logger.info(f"{'='*80}")
    logger.info(f"Video URL: {video_url}")
    logger.info(f"Start: {start_time}s, End: {end_time}s, Duration: {end_time - start_time}s")
    
    try:
        import yt_dlp
        
        final_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        duration = end_time - start_time
        
        # Get direct video URL
        logger.info(f"⚡ STEP 1: Getting direct video URL...")
        
        ydl_opts = {
            'format': f'best[height<={quality}][ext=mp4]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        
        # Add cookies
        cookies_content = os.environ.get('YOUTUBE_COOKIES')
        if cookies_content:
            cookies_file = os.path.join(TEMP_DIR, 'cookies.txt')
            with open(cookies_file, 'w') as f:
                f.write(cookies_content)
            ydl_opts['cookiefile'] = cookies_file
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            direct_url = info['url']
        
        logger.info(f"✅ Got direct URL")
        
        # FFmpeg PRECISE re-encode
        logger.info(f"🎯 STEP 2: Precise re-encode with optimized compression...")
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-i', direct_url,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '26',
            '-c:a', 'aac',
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
        
        logger.info(f"Running FFmpeg precise re-encode...")
        
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr[:500]}")
            raise Exception(f"FFmpeg failed: {result.stderr[:200]}")
        
        logger.info("FFmpeg complete")
        
        if os.path.exists(final_path):
            file_size = os.path.getsize(final_path)
            logger.info(f"✅ PRECISE SUCCESS: {file_size} bytes")
            return final_path, f"✅ Downloaded (Precise, {file_size // 1024}KB, exact timestamps)"
        
        raise Exception("Output file not created")
        
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout!")
        return None, "❌ Timeout - clip too long"
        
    except Exception as e:
        logger.error(f"❌ Precise download failed: {str(e)}", exc_info=True)
        return None, f"❌ Error: {str(e)[:150]}"

def trim_preview_video(preview_path, trim_start_relative, trim_end_relative, output_name, crop_vertical):
    """
    Trim the preview video based on RELATIVE user adjustments
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"=== TRIMMING PREVIEW ===")
    logger.info(f"{'='*80}")
    
    try:
        final_path = os.path.join(OUTPUT_DIR, f"{output_name}.mp4")
        
        # Calculate duration from relative timestamps
        duration = trim_end_relative - trim_start_relative
        
        logger.info(f"Trimming preview: start={trim_start_relative}s (relative), duration={duration}s")
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-ss', str(trim_start_relative),
            '-i', preview_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '26',
            '-c:a', 'aac',
            '-b:a', '128k',
        ]
        
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
        
        logger.info(f"Running FFmpeg trim...")
        
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=180
        )
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr[:500]}")
            raise Exception(f"FFmpeg failed: {result.stderr[:200]}")
        
        if os.path.exists(final_path):
            file_size = os.path.getsize(final_path)
            logger.info(f"✅ TRIM SUCCESS: {file_size} bytes")
            return final_path, f"✅ Trimmed ({file_size // 1024}KB, exact timestamps)"
        
        raise Exception("Output file not created")
        
    except Exception as e:
        logger.error(f"❌ Trim failed: {str(e)}", exc_info=True)
        return None, f"❌ Error: {str(e)[:150]}"

def download_clip(video_url, start_time, end_time, output_name, quality, crop_vertical, precise_mode):
    """
    Universal download function - routes to fast or precise method
    """
    if precise_mode:
        return download_clip_precise(video_url, start_time, end_time, output_name, quality, crop_vertical)
    else:
        return download_clip_fast(video_url, start_time, end_time, output_name, quality, crop_vertical)

# Global state
search_results = []
selected_video = None
current_preview_path = None
current_buffer_start = 0
current_buffer_end = 0
current_clip_info = {}

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

def generate_preview_handler(timestamps_text, quality):
    """Generate preview for first clip with RELATIVE timestamps"""
    global selected_video, current_preview_path, current_buffer_start, current_buffer_end, current_clip_info
    
    if selected_video is None:
        return None, "❌ No video selected", gr.update(visible=False), gr.update(), gr.update(), ""
    
    if not timestamps_text or timestamps_text.strip() == "":
        return None, "❌ Please enter timestamps", gr.update(visible=False), gr.update(), gr.update(), ""
    
    clips = parse_timestamps(timestamps_text)
    
    if not clips:
        return None, "❌ No valid timestamps", gr.update(visible=False), gr.update(), gr.update(), ""
    
    # Generate preview for first clip
    first_clip = clips[0]
    
    preview_path, buffer_start, buffer_end, preview_duration, msg = generate_preview(
        selected_video['url'],
        first_clip['start_sec'],
        first_clip['end_sec'],
        "clip_1",
        quality
    )
    
    if preview_path:
        current_preview_path = preview_path
        current_buffer_start = buffer_start
        current_buffer_end = buffer_end
        
        # Calculate RELATIVE timestamps (0 = start of preview)
        original_start_relative = first_clip['start_sec'] - buffer_start  # e.g., 5s
        original_end_relative = first_clip['end_sec'] - buffer_start      # e.g., 15s
        
        # Store clip info
        current_clip_info = {
            'original_start': first_clip['start'],
            'original_end': first_clip['end'],
            'start_relative': original_start_relative,
            'end_relative': original_end_relative,
            'preview_duration': preview_duration
        }
        
        info_text = f"""✅ **Preview Ready!**

📊 **Original timestamps:** {first_clip['start']} - {first_clip['end']} (from source video)
🎬 **Preview duration:** {preview_duration:.1f} seconds (includes 5s buffer on each side)

💡 **How to use:**
1. Watch the preview video above
2. Your clip starts at **{original_start_relative:.1f}s** and ends at **{original_end_relative:.1f}s** in the preview
3. Adjust the sliders below to fine-tune (sliders show seconds from preview start)
4. Click "Download" when satisfied

⏱️ **Slider range:** 0s to {preview_duration:.1f}s (entire preview video)
"""
        
        clip_info_text = f"📌 Current selection: {original_start_relative:.1f}s to {original_end_relative:.1f}s (Duration: {original_end_relative - original_start_relative:.1f}s)"
        
        return (
            preview_path,
            info_text,
            gr.update(visible=True),
            gr.update(value=original_start_relative, minimum=0, maximum=preview_duration, step=0.1),
            gr.update(value=original_end_relative, minimum=0, maximum=preview_duration, step=0.1),
            clip_info_text
        )
    
    return None, msg, gr.update(visible=False), gr.update(), gr.update(), ""

def update_clip_info(start, end):
    """Update the clip duration display"""
    duration = end - start
    return f"📌 Current selection: {start:.1f}s to {end:.1f}s (Duration: {duration:.1f}s / {format_duration(int(duration))})"

def download_from_preview(clip_name, trim_start_relative, trim_end_relative, crop_vertical):
    """Download using RELATIVE timestamps from preview"""
    global current_preview_path, current_buffer_start
    
    if current_preview_path is None:
        return "❌ No preview available", []
    
    if not os.path.exists(current_preview_path):
        return "❌ Preview file not found", []
    
    if trim_start_relative >= trim_end_relative:
        return "❌ Start time must be before end time", []
    
    logger.info(f"Downloading from preview: {trim_start_relative}s to {trim_end_relative}s (relative)")
    
    file_path, msg = trim_preview_video(
        current_preview_path,
        trim_start_relative,
        trim_end_relative,
        clip_name if clip_name.strip() else "clip_1",
        crop_vertical
    )
    
    if file_path and os.path.exists(file_path):
        return f"✅ Downloaded from preview!\n{msg}\n\n💡 Tip: Check the video before closing - files are deleted when session ends!", [file_path]
    
    return f"❌ Download failed: {msg}", []

def process_download(timestamps_text, clip_name_prefix, quality, crop_vertical, precise_mode):
    """Process and download all clips (original method)"""
    global selected_video
    
    logger.info(f"\n{'='*80}")
    logger.info(f"=== PROCESSING DOWNLOAD REQUEST ===")
    logger.info(f"{'='*80}")
    
    if selected_video is None:
        logger.warning("No video selected")
        return "❌ No video selected", []
    
    mode_name = "Precise Mode 🎯" if precise_mode else "Fast Mode ⚡"
    
    logger.info(f"Video: {selected_video['title']}")
    logger.info(f"URL: {selected_video['url']}")
    logger.info(f"Mode: {mode_name}")
    
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
    
    mode_emoji = "🎯" if precise_mode else "⚡"
    status_lines = [f"{mode_emoji} Processing {len(clips)} clips using {mode_name}"]
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
            precise_mode
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
    ### Search YouTube → Select Video → Enter Timestamps → Preview & Edit → Download
    
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
                value="480",
                label="Quality"
            )
        
        # PREVIEW & EDIT SECTION
        gr.Markdown("---")
        gr.Markdown("### 🎬 Option 1: Preview & Edit (Recommended for Single Clip)")
        
        preview_btn = gr.Button("🎥 GENERATE PREVIEW (First Clip Only)", variant="secondary", size="lg")
        preview_status = gr.Markdown("Preview Status")
        
        with gr.Column(visible=False) as preview_editor:
            preview_video = gr.Video(label="📹 Preview Video (Watch First!)")
            
            gr.Markdown("### ✂️ Fine-Tune Timestamps")
            gr.Markdown("**The sliders below show seconds from the START of the preview video (0 = preview start)**")
            
            with gr.Row():
                trim_start_slider = gr.Slider(
                    label="⏩ Start Time (seconds from preview start)",
                    minimum=0,
                    maximum=30,
                    step=0.1,
                    value=5,
                    interactive=True
                )
                trim_end_slider = gr.Slider(
                    label="⏸️ End Time (seconds from preview start)",
                    minimum=0,
                    maximum=30,
                    step=0.1,
                    value=15,
                    interactive=True
                )
            
            clip_duration_display = gr.Textbox(
                label="📊 Current Selection",
                interactive=False,
                lines=1,
                value="Clip info will appear here"
            )
            
            crop_checkbox_preview = gr.Checkbox(
                label="✅ Crop to 9:16 Vertical (for TikTok/Reels/Shorts)", 
                value=False
            )
            
            download_preview_btn = gr.Button("📥 DOWNLOAD WITH ADJUSTED SETTINGS", variant="primary", size="lg")
            download_preview_status = gr.Textbox(label="Download Status", lines=3, interactive=False)
            download_preview_files = gr.File(label="📦 Downloaded Clip", file_count="single")
        
        # DIRECT DOWNLOAD SECTION
        gr.Markdown("---")
        gr.Markdown("### 🚀 Option 2: Direct Batch Download (No Preview)")
        
        precise_mode = gr.Radio(
            choices=[
                ("⚡ Fast Mode (30-60 sec, ±2s accuracy)", False),
                ("🎯 Precise Mode (2-3 min, exact timestamps, smaller files)", True)
            ],
            value=True,
            label="Processing Mode",
            info="Fast: Stream copy (quick but ±2s) | Precise: Re-encode (slower but exact + optimized file size)"
        )
        
        crop_checkbox = gr.Checkbox(
            label="✅ Crop to 9:16 Vertical (requires Precise mode)", 
            value=False
        )
        
        download_btn = gr.Button("📥 DOWNLOAD ALL CLIPS", variant="primary", size="lg")
        
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
    
    # Preview handlers
    preview_btn.click(
        fn=generate_preview_handler,
        inputs=[timestamps_input, quality_select],
        outputs=[preview_video, preview_status, preview_editor, trim_start_slider, trim_end_slider, clip_duration_display]
    )
    
    # Update clip info when sliders change
    trim_start_slider.change(
        fn=update_clip_info,
        inputs=[trim_start_slider, trim_end_slider],
        outputs=[clip_duration_display]
    )
    
    trim_end_slider.change(
        fn=update_clip_info,
        inputs=[trim_start_slider, trim_end_slider],
        outputs=[clip_duration_display]
    )
    
    download_preview_btn.click(
        fn=download_from_preview,
        inputs=[clip_name, trim_start_slider, trim_end_slider, crop_checkbox_preview],
        outputs=[download_preview_status, download_preview_files]
    )
    
    # Direct download handler
    download_btn.click(
        fn=process_download,
        inputs=[timestamps_input, clip_name, quality_select, crop_checkbox, precise_mode],
        outputs=[download_status, download_files]
    )
    
    gr.Markdown("""
    ---
    ### 💡 Tips & Guide:
    
    **Timestamp format:** Use `2:30-3:15` (minutes:seconds), one per line
    
    ### 🎬 Two Workflows:
    
    **🎯 Option 1: Preview & Edit (Recommended for Perfect Clips)**
    1. Enter approximate timestamps (e.g., `2:30-3:15`)
    2. Click "Generate Preview" → Get fast preview with 5s buffer
    3. Watch the preview video
    4. Adjust sliders (showing seconds from preview start, e.g., 5.2s to 15.8s)
    5. Download with exact timestamps!
    
    **⚡ Option 2: Direct Batch Download (For Multiple Clips)**
    - Download all clips at once
    - Choose Fast (±2s, ~30 MB) or Precise (exact, ~25-35 MB)
    - Good when timestamps are already accurate
    
    ### 📊 Mode Comparison:
    | Feature | Fast Mode ⚡ | Precise Mode 🎯 | Preview & Edit 🎬 |
    |---------|-------------|-----------------|-------------------|
    | **Speed** | 30-60 sec | 2-3 min | 45 sec preview + 2 min encode |
    | **File Size** | ~30 MB | ~25-35 MB | ~25-35 MB |
    | **Accuracy** | ±2-4 sec | Exact | Exact (user-adjusted) |
    | **Quality** | Original | High (CRF 26) | High (CRF 26) |
    | **Best for** | Quick previews | Batch precise | Single perfect clip |
    
    ### 🔧 Technical Details:
    - **Fast Mode:** Stream copy (no re-encoding, keyframe-accurate)
    - **Precise Mode:** Re-encodes with `fast` preset + CRF 26 (optimized compression)
    - **Preview:** Fast stream copy with 5s buffer, then precise re-encode on download
    - **Vertical Crop:** Scales to 1080x1920 (9:16 ratio) for TikTok/Reels/Shorts
    
    ⚠️ **Important:** All files are temporary and deleted when session ends. Download immediately!
    
    📝 **Check Render logs** if downloads fail (Dashboard → Logs tab)
    """)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting app on port {port}")
    app.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False
    )
