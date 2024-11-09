import streamlit as st
import yt_dlp
import imageio_ffmpeg as ffmpeg
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import qrcode
from PIL import Image, ImageDraw, ImageFont
import pyshorteners
import io
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_video(video_url, download_path, audio_only, download_transcript, start_time, end_time):
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes', 1)
                progress = int((downloaded_bytes / total_bytes) * 100)
                st.session_state['progress'] = progress

        # Get the ffmpeg executable path from imageio_ffmpeg
        ffmpeg_path = ffmpeg.get_ffmpeg_exe()

        ydl_opts = {
            'progress_hooks': [progress_hook],
            'outtmpl': f'{download_path}/%(title)s.%(ext)s',
            'logger': logger,
            'ffmpeg_location': ffmpeg_path  # Use ffmpeg from imageio-ffmpeg
        }

        if audio_only:
            ydl_opts['format'] = 'bestaudio'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        if start_time or end_time:
            # Use FFmpeg to trim the video after downloading
            ydl_opts['postprocessors'] = ydl_opts.get('postprocessors', []) + [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4'
            }]
            ydl_opts['postprocessor_args'] = []
            if start_time:
                ydl_opts['postprocessor_args'].extend(['-ss', start_time])
            if end_time:
                ydl_opts['postprocessor_args'].extend(['-to', end_time])

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        if download_transcript:
            download_transcript_func(video_url, download_path)

        st.session_state['status'] = 'Download complete.'

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state['status'] = f'Error occurred: {e}'

def download_playlist(playlist_url, download_path, start_index):
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes', 1)
                progress = int((downloaded_bytes / total_bytes) * 100)
                st.session_state['progress'] = progress

        # Get the ffmpeg executable path from imageio_ffmpeg
        ffmpeg_path = ffmpeg.get_ffmpeg_exe()

        ydl_opts = {
            'progress_hooks': [progress_hook],
            'outtmpl': f'{download_path}/%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s',
            'noplaylist': False,
            'playliststart': start_index,
            'logger': logger,
            'ffmpeg_location': ffmpeg_path  # Use ffmpeg from imageio-ffmpeg
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(playlist_url, download=False)
            for idx, entry in enumerate(info_dict['entries'], start=start_index):
                st.session_state['status'] = f"Downloading video {idx}: {entry['title']}"
                ydl.download([entry['webpage_url']])

        st.session_state['status'] = 'Download complete.'

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state['status'] = f'Error occurred: {e}'

def download_transcript_func(video_url, download_path):
    try:
        video_id = video_url.split('v=')[-1].split('&')[0]
        transcript = YouTubeTranscriptApi.get_transcript(video_id)

        transcript_text = ""
        for entry in transcript:
            transcript_text += f"{entry['start']:.2f} - {entry['text']}\n"

        transcript_file = f"{download_path}/{video_id}_transcript.txt"
        with open(transcript_file, 'w') as file:
            file.write(transcript_text)
        logger.info(f"Transcript downloaded successfully: {transcript_file}")

    except TranscriptsDisabled:
        logger.warning("Transcripts are disabled for this video.")
        st.session_state['status'] = 'Transcripts are disabled for this video.'
    except NoTranscriptFound:
        logger.warning("No transcript found for this video.")
        st.session_state['status'] = 'No transcript found for this video.'
    except Exception as e:
        logger.error(f"An error occurred while downloading transcript: {e}")
        st.session_state['status'] = f'Error occurred while downloading transcript: {e}'

def generate_qr_code(data_to_encode, title):
    # Generate QR code with high error correction level
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction
        version=1,
        box_size=10,
        border=4
    )
    qr.add_data(data_to_encode)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color='black', back_color='white').convert('RGB')

    # Embed YouTube video logo in the middle of the QR code
    youtube_logo_path = 'youtube_logo.png'  # Path to the YouTube logo image
    if os.path.exists(youtube_logo_path):
        youtube_logo = Image.open(youtube_logo_path).convert('RGBA')
        # Resize the YouTube logo
        qr_width, qr_height = img_qr.size
        logo_size = qr_width // 4  # Adjust logo size relative to QR code size
        youtube_logo = youtube_logo.resize((logo_size, logo_size), Image.LANCZOS)
        # Calculate position to paste the logo
        pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
        # Paste the logo into the QR code
        img_qr.paste(youtube_logo, pos, mask=youtube_logo)

    img = img_qr  # Proceed with img as the final QR code image

    # Add title to the QR code image if provided
    if title:
        img_width, img_height = img.size

        # Try to use a TrueType font
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except IOError:
            font = ImageFont.load_default()

        draw = ImageDraw.Draw(img)

        # Calculate the width and height of the text to be added
        bbox = draw.textbbox((0, 0), title, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Create a new image with extra space for the title
        total_height = img_height + text_height + 10
        new_img = Image.new('RGB', (img_width, total_height), 'white')

        # Paste the QR code onto the new image
        new_img.paste(img, (0, text_height + 10))

        # Add the title text to the new image
        draw = ImageDraw.Draw(new_img)
        text_position = ((img_width - text_width) / 2, 5)
        draw.text(text_position, title, fill='black', font=font)

        img = new_img

    # Convert the image to bytes
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    byte_im = buf.getvalue()

    return byte_im

def main():
    st.title('Simple YouTube Downloader with QR Code Generator')

    # User Guide
    st.markdown('''**User Guide:**
    This tool is designed to make using YouTube videos in educational settings easier. You can download the video or choose just the audio. You can also select to download portions of the video with specific start and end times. Choose to download the transcript as well. The tool also includes a QR code generator that can be used to share the video with others as well as a URL shortener to make the URL more readable.
    - Select the appropriate download type (Video or Playlist).
    - Support the development: [Support me on BuyMeACoffee](https://buymeacoffee.com/geraldinebengsch)
    ''')

    # Download Type selection
    download_type = st.radio('Select Download Type', ['Video', 'Playlist'], key='download_type')

    # Video/Playlist URL input
    video_url = st.text_input('YouTube URL:', key='video_url')

    # Download Path input
    download_path = st.text_input('Download Path (optional, default is current folder):', value='.', key='download_path')

    # Video specific options
    if download_type == 'Video':
        # Audio Only checkbox
        audio_only = st.checkbox('Download audio only', key='audio_only')

        # Download Transcript checkbox
        download_transcript = st.checkbox('Download transcript', key='download_transcript')

        # Start and End Time inputs
        start_time = st.text_input('Start Time (optional, e.g., 00:01:00):', key='start_time')
        end_time = st.text_input('End Time (optional, e.g., 00:02:00):', key='end_time')

    # Playlist specific options
    if download_type == 'Playlist':
        # Start Index input
        start_index = st.number_input('Starting video index (default is 1):', min_value=1, value=1, key='start_index')

    # Download Button
    if st.button('Download'):
        if not video_url:
            st.warning('Please enter a valid YouTube URL.')
        else:
            st.session_state['progress'] = 0
            st.session_state['status'] = 'Starting download...'
            if download_type == 'Video':
                download_video(
                    st.session_state['video_url'],
                    st.session_state['download_path'],
                    st.session_state['audio_only'],
                    st.session_state['download_transcript'],
                    st.session_state['start_time'],
                    st.session_state['end_time']
                )
            elif download_type == 'Playlist':
                download_playlist(
                    st.session_state['video_url'],
                    st.session_state['download_path'],
                    st.session_state['start_index']
                )

    # Progress Bar
    if 'progress' in st.session_state:
        st.progress(st.session_state['progress'] / 100)

    # Status
    if 'status' in st.session_state:
        st.write(st.session_state['status'])

    # QR Code Generator Section
    st.header("QR Code Generator")

    # Option to shorten URL
    shorten_option = st.checkbox("Shorten URL before generating QR code")

    # Input for the title
    qr_title = st.text_input("Enter title to add to the QR code image:")

    if video_url:
        # Shorten the URL if the option is selected
        if shorten_option:
            s = pyshorteners.Shortener()
            try:
                short_url = s.tinyurl.short(video_url)
                st.write(f"Shortened URL: {short_url}")
                data_to_encode = short_url
            except Exception as e:
                st.error(f"Error shortening URL: {e}")
                data_to_encode = video_url
        else:
            data_to_encode = video_url

        # Generate QR code
        byte_im = generate_qr_code(data_to_encode, qr_title)

        # Display the QR code image
        st.image(byte_im)

        # Provide a download button
        st.download_button(
            label="Download QR Code",
            data=byte_im,
            file_name='qr_code.png',
            mime='image/png'
        )


if __name__ == "__main__":
    if 'progress' not in st.session_state:
        st.session_state['progress'] = 0
    if 'status' not in st.session_state:
        st.session_state['status'] = 'Idle'
    main()
