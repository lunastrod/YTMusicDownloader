import subprocess
import os
import re
import sys
import concurrent.futures
from urllib.parse import urlparse, parse_qs
import mutagen
import mutagen.id3
import syncedlyrics

"""
how main works:
setup():
    creates txt files
    creates Songs and Temp directories
    updates yt-dlp
main():
    reads input urls from _Input.txt
    reads params from _Params.txt
    checks which videos are already downloaded by reading the metadata of the files in Songs
    downloads the videos that are not already downloaded using yt-dlp and ffmpeg
    asks the user if they want to delete files in Songs that are not in the expected files list
    cleans up the Temp directory

TODO:
    - Custom output directory
    x Lyrics added to metadata (use syncedlyrics python library)
    x Better output file naming
    x only get artist title album and date from yt-dlp metadata
"""





# PATH FUNTIONS =========================================================
def get_resource_path(*relative_path):
    """ Get absolute path to resource from relative path. """
    if getattr(sys, 'frozen', False):
        # PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        # Script mode
        base_path = os.getcwd()
    return os.path.join(base_path, *relative_path)

def normalize_path(path):
    """
    Normalizes a user-provided path, making it absolute.

    If the path is relative (e.g., "Songs"), it is joined with the
    current working directory. If it is already an absolute path
    (e.g., "C:\\Songs" or "\\\\Server\\Songs"), it is returned as is.

    Args:
        user_input_path (str): The path string from the user.

    Returns:
        str: The normalized, absolute path.
    """
    if os.path.isabs(path):
        return path
    else:
        return os.path.abspath(os.path.join(os.getcwd(), path))








# GLOBAL VARIABLES ================================================
input_file_path = os.path.join(os.getcwd(), "_Input.txt")
instructions_file_path = os.path.join(os.getcwd(), "_Instructions.txt")
params_file_path = os.path.join(os.getcwd(), "_Params.txt")
global songs_path
temp_path = os.path.join(os.getcwd(), "temp")
yt_dlp_path = get_resource_path("src", "yt-dlp.exe")
ffmpeg_path = get_resource_path("src", "ffmpeg.exe")












# OTHER FUNCTIONS ================================================
def colortxt(color, text):
    """ Color text for console output. """
    colors = {
        'R': '\033[91m',  # Red
        'G': '\033[92m',  # Green
        'Y': '\033[93m',  # Yellow
        'B': '\033[94m',  # Blue
        'M': '\033[95m',  # Magenta
        'C': '\033[96m',  # Cyan
        'W': '\033[0m',   # White/Reset
    }
    return colors.get(color, '\033[0m') + text + colors['W']

def clean_directory(path):
    """ Delete all files in a directory. """
    # Delete all files in the directory
    for filename in os.listdir(path):
        file_path = os.path.join(path, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except Exception as e:
            print(colortxt("R", f"Error deleting file {file_path}: {e}"))














# YT-DLP FUNCTIONS ================================================

def is_playlist(url):
    # Parse the URL
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    valid_hosts = ["youtube.com", "youtu.be", "music.youtube.com", "www.youtube.com", "m.youtube.com"]
    
    # Normalize the domain by removing 'www.' if present
    netloc = parsed_url.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    
    # Check if the host is a valid YouTube domain
    if netloc in valid_hosts:
        # Check if the URL path contains 'playlist' or if the query contains 'list'
        if 'list' in query_params:
            return True
    return False


def is_video(url):
    # Parse the URL
    parsed_url = urlparse(url)
    valid_hosts = ["youtube.com", "youtu.be", "music.youtube.com", "www.youtube.com", "m.youtube.com"]
    
    # Normalize the domain by removing 'www.' if present
    netloc = parsed_url.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    
    # Check if the host is a valid YouTube domain
    if netloc in valid_hosts:
        # For youtu.be, the video ID is in the path
        if netloc == "youtu.be":
            return True
        # For other YouTube domains, check if the URL path contains 'watch'
        if 'watch' in parsed_url.path or 'v=' in parsed_url.query:
            return True
    return False

def get_playlist_videos(url):
    """ Get video IDs from a YouTube playlist URL. """
    command = [
        yt_dlp_path,
        "--flat-playlist",
        "--get-id",
        url
    ]

    # Run yt-dlp command
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(colortxt("R", f"Error fetching playlist videos: {result.stderr}"))
        return []
    return result.stdout



def download_video(url):
    command = [
        yt_dlp_path,
        "--ffmpeg-location", os.path.dirname(ffmpeg_path),
        "-P", "home:" + songs_path,
        "-P", "temp:" + temp_path,
        "-N", "6",
        "--format", "bestaudio",
        "-x",
        "--audio-format", "mp3",
        "--embed-thumbnail",
        "--embed-metadata",
        "--restrict-filenames",
        "--ppa", "EmbedThumbnail+ffmpeg_o:-c:v mjpeg -vf crop=\"'if(gt(ih,iw),iw,ih)':'if(gt(iw,ih),ih,iw)'\"",#crop to square image
        "--print", "after_move:%(filepath)s",
        "-o", "%(artist,uploader)s - %(title)s.%(ext)s",
        url
    ]

    # Run yt-dlp command
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(colortxt("R", f"Error downloading video: {result.stderr}"))
        return

    # Get the output file path from the command result
    output_file = result.stdout.strip()

    delete_unwanted_metadata(output_file)
    fix_title(output_file)
    metadata = read_metadata(output_file)

    fetch_lyrics(output_file)

    # rename file to "artist - title.mp3"
    new_filename = f"{metadata.get('artist', ['Unknown Artist'])[0]} - {metadata.get('title', ['Unknown Title'])[0]}.mp3"
    new_filepath = os.path.join(songs_path, new_filename)
    try:
        os.rename(output_file, new_filepath)
    except Exception as e:
        print(colortxt("R", f"Error renaming file {output_file} to {new_filepath}: {e}"))
        print(colortxt("Y", f"The song {new_filename} is probably repeated, skipping..."))
        return
    output_file = new_filepath

    if os.path.exists(output_file):
        write_url_metadata(output_file, url) # Write the URL to the metadata
        url = read_url_metadata(output_file)
        print(colortxt("B", f"Downloaded: {output_file}"))
        print(colortxt("B", f"  Metadata: {metadata}"))
        print(colortxt("B", f"  URL: {url}"))
        return output_file
    else:
        print(colortxt("R", f"Error: Output file {output_file} does not exist."))
        return output_file



        







# METADATA FUNCTIONS ================================================
def read_metadata(filename):
    """ Read metadata from an audio file. """
    try:
        audio = mutagen.File(filename, easy=True)
        if audio is None:
            print(colortxt("R", f"Error reading metadata for {filename}"))
            return None
        return audio.tags
    except Exception as e:
        print(colortxt("R", f"An error occurred while reading {filename}: {e}"))
        return None
    
def delete_unwanted_metadata(filename):
    """ Deletes everything except artist, title, album and date from the audio file's metadata. """
    try:
        audio = mutagen.File(filename, easy=True)
        if audio is None:
            print(colortxt("R", f"Error reading metadata for {filename}"))
            return False
        allowed_tags = ['artist', 'title', 'album', 'date']
        tags_to_delete = [tag for tag in audio.keys() if tag not in allowed_tags]
        for tag in tags_to_delete:
            del audio[tag]
        audio.save()
        return True
    except Exception as e:
        print(colortxt("R", f"An error occurred while deleting metadata from {filename}: {e}"))
        return False
    

    
def fix_title(filename):
    title=read_metadata(filename).get('title', ['Unknown Title'])[0]
    artist=read_metadata(filename).get('artist', ['Unknown Artist'])[0]

    # Remove common unwanted substrings from filenames
    unwanted_substrings = ["(Official Video)",
                           "(Official Audio)",
                           "(Official Version)",
                           "(Video)",
                           "(Official Lyric Video)",
                           "(Official Music Video)",
                           "(Official Visualizer)",
                           "(Soundtrack Version)",
                           "Official_Video",
                           "(4K Remaster)",
                           "?",
                           "’",
    ]
    for substring in unwanted_substrings:
        title = title.replace(substring, "")

    #remove artist name from title if present
    title = re.sub(rf"(?i)\b{re.escape(artist)}\b|\b{re.escape(artist.replace(' ', '_'))}\b", "", title)

    # Special titles
    special_titles = {"★★★★★": "5 Stars"}
    if title in special_titles:
        title = special_titles[title]

    # Remove any stray hyphens at the beginning or end of the string
    title = title.strip(' -')

    # write the fixed title back to metadata
    try:
        audio = mutagen.File(filename, easy=True)
        if audio is None:
            print(colortxt("R", f"Error reading metadata for {filename}"))        
        audio['title'] = title
        audio.save()
    except Exception as e:
        print(colortxt("R", f"An error occurred while writing {filename}: {e}"))

def write_url_metadata(filename, video_url):
    """ Write the video URL to the audio file's metadata. """
    try:
        audio = mutagen.id3.ID3(filename)
        audio.add(mutagen.id3.WXXX(
            encoding=3,
            desc="MusicVideoURL",
            url=video_url
        ))
        audio.save()
        return True
    except Exception as e:
        print(colortxt("R", f"An error occurred while writing {filename}: {e}"))
        return False

    
def read_url_metadata(filename):
    """ Read the video URL from the audio file's metadata. """
    try:
        audio = mutagen.id3.ID3(filename)
        for tag in audio.getall("WXXX"):
            if tag.desc == "MusicVideoURL":
                return tag.url  # Return the URL stored in the WXXX frame
        return None
    
    except Exception as e:
        print(colortxt("R", f"An error occurred while reading {filename}: {e}"))
        return None









# LYRICS FUNCTIONS ================================================
def fetch_lyrics(filename):
    """ Fetch lyrics for a given audio file """
    metadata = read_metadata(filename)
    title=metadata.get('title', ['Unknown Title'])[0]
    artist=metadata.get('artist', ['Unknown Artist'])[0]
    try:
        lyrics = syncedlyrics.search(f"{artist} {title}")
    except Exception as e:
        print(colortxt("R", f"An error occurred while fetching lyrics for {artist} - {title}: {e}"))
        return
    
    # Embed the lyrics into the MP3 metadata
    try:
        # Create a new USLT frame for the lyrics
        audio = mutagen.id3.ID3(filename)
        uslt = mutagen.id3.USLT(encoding=3, lang='eng', desc='Lyrics', text=lyrics)
        audio.add(uslt)
        audio.save()
        print(colortxt("B", f"Lyrics embedded for {artist} - {title}"))
    except Exception as e:
        print(colortxt("R", f"An error occurred while embedding lyrics for {artist} - {title}: {e}"))
    









# SETUP AND MAIN FUNCTIONS ================================================

def setup():
    # Check if _Input.txt doesnt exist
    if not os.path.exists(input_file_path) or os.path.getsize(input_file_path) == 0:
        # Create the file if it doesn't exist
        with open(input_file_path, 'w') as f:
            f.write("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            print(colortxt("Y", f"File '{input_file_path}' not found or empty. Created with default URL."))

    # Create instrutions file if it doesn't exist
    if not os.path.exists(instructions_file_path):
        with open(instructions_file_path, 'w') as f:
            f.write("Instructions:\n")
            f.write("Add YouTube video URLs or playlist URLs to '_Input.txt'.\n")
            f.write("Run the .exe to download the music.\n")
            print(colortxt("Y", f"File '{instructions_file_path}' not found. Created with instructions."))

    # Create params file if it doesn't exist
    if not os.path.exists(params_file_path):
        with open(params_file_path, 'w') as f:
            f.write("output=Songs\n")
            print(colortxt("Y", f"File '{params_file_path}' not found. Created with parameters."))

    global songs_path

    with open(params_file_path, 'r') as f:
        for line in f:
            if line.startswith("output="):
                try:
                    songs_path = normalize_path(line.split("=", 1)[1].strip())
                    os.makedirs(songs_path, exist_ok=True)
                    print(colortxt("B", f"Output directory set to: {songs_path}"))
                except Exception as e:
                    print(colortxt("R", f"Error creating output directory: {e}"))
                    exit(1)

    # Ensure the directories exist
    os.makedirs(songs_path, exist_ok=True)
    os.makedirs(temp_path, exist_ok=True)
    clean_directory(temp_path)

    # Check if yt-dlp is available
    if not os.path.exists(yt_dlp_path):
        print(colortxt("R", "yt-dlp not found. Please ensure it is in the 'src' directory."))
        exit(1)

    # Check if ffmpeg is available
    if not os.path.exists(ffmpeg_path):
        print(colortxt("R", "ffmpeg not found. Please ensure it is in the 'src' directory."))
        exit(1)
    
    # Update yt-dlp to the latest version
    try:
        subprocess.run([yt_dlp_path, "-U"], check=True)
        print(colortxt("B", "yt-dlp updated to the latest version."))
    except subprocess.CalledProcessError as e:
        print(colortxt("R", f"Error updating yt-dlp: {e}"))
        exit(1)


def main():
    print(colortxt("B", "Starting YouTube Video Downloader..."))
    print(colortxt("B","Luna, 2025"))
    #read the input URL from the file 
    with open(input_file_path, 'r') as f:
        input_url = f.read().strip()

    threads = 20 #number of threads to use

    url_list = []
    for line in input_url.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):  # Skip empty lines and comments
            continue
        if is_video(line):
            url_list.append(line)
        elif is_playlist(line):
            playlist_urls = get_playlist_videos(line).splitlines()
            for i in range(len(playlist_urls)):
                playlist_urls[i] = "https://www.youtube.com/watch?v=" + playlist_urls[i]
            url_list.extend(playlist_urls)
        else:
            print(colortxt("R", f"Invalid URL: {line}"))

    # Remove duplicates
    url_list = list(set(url_list))

    expected_files = []
    # Remove videos that are already downloaded
    for file in os.listdir(songs_path):
        file_path = os.path.abspath(os.path.join(songs_path, file))
        if os.path.isfile(file_path):
            try:
                video_url = read_url_metadata(file_path)
                if video_url in url_list:
                    url_list.remove(video_url)
                    
                    print(colortxt("B", f"Video already downloaded: {file}"))
                    print(colortxt("B", f"  Metadata: {read_metadata(file_path)}"))
                    print(colortxt("B", f"  URL: {video_url}"))
                    expected_files.append(file_path)
            except Exception as e:
                print(colortxt("R", f"Error reading metadata for {file_path}: {e}"))
                continue
    
    print(colortxt("B", f"Found {len(url_list)} videos to download."))
    effective_threads = min(threads, len(url_list), 50)
    # Download videos using multithreading
    if effective_threads > 0:
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_threads) as executor:
            future_to_url = {executor.submit(download_video, url): url for url in url_list}
            for future in concurrent.futures.as_completed(future_to_url):
                #future.result()
                file_path = future.result()
                expected_files.append(file_path)

    # ask user if they want to delete songs not in expected_files
    for file in os.listdir(songs_path):
        file_path = os.path.abspath(os.path.join(songs_path, file))
        if os.path.isfile(file_path):
            if file_path not in expected_files:
                print(colortxt("Y", f"File {file} not in expected files."))
                delete = input(colortxt("Y", f"Do you want to delete {file}? (y/n) "))
                if delete.lower() == 'y':
                    try:
                        os.remove(file_path)
                        print(colortxt("B", f"Deleted {file}."))
                    except Exception as e:
                        print(colortxt("R", f"Error deleting file {file}: {e}"))
    
    clean_directory(temp_path)  # Clean up Temp setupdirectory
    try:
        os.rmdir(temp_path)
    except OSError as e:
        print(colortxt("R", f"Error deleting temp directory: {e}"))

if __name__ == "__main__":
    setup()
    main()
    input("Press Enter to exit...")