import mutagen
import os
import unicodedata

songs_path = os.path.join(os.getcwd(), "Songs")

def colortxt(color, text):
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

def read_metadata(file_path):
    #reads artist, title
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio is None:
            print(colortxt("R", f"Error reading {file_path}"))
            return None
        return  {
                    'artist': audio.get('artist', [None])[0],
                    'title': audio.get('title', [None])[0],
                }
    except Exception as e:
        print(colortxt("R", f"Error reading {file_path}: {e}"))
        return None
    
def delete_metadata(file_path):
    #deletes all metadata except artist, title, album
    try:
        audio = mutagen.File(file_path, easy=True)
        if audio is None:
            print(colortxt("R", f"Error reading {file_path}"))
            return None
        for key in list(audio.keys()):
            if key not in ['artist', 'title', 'album', 'date']:
                print(colortxt("B", f"Deleting {key} from {file_path}"))
                del audio[key]
        audio.save()
    except Exception as e:
        print(colortxt("R", f"Error deleting metadata from {file_path}: {e}"))

def rename_file(file_path, artist, title):
    # Normalize and sanitize artist and title
    artist = unicodedata.normalize('NFKD', artist).encode('ascii', 'ignore').decode('ascii')
    title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')

    # Remove invalid characters from base name
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    base_name = f"{artist} - {title}"
    for char in invalid_chars:
        base_name = base_name.replace(char, "")

    # Create initial filename and path
    new_file_name = f"{base_name}.mp3"
    new_file_path = os.path.join(songs_path, new_file_name)

    # Handle name collisions
    if (file_path == new_file_path):
        #print(colortxt("B", f"File {file_path} already has the correct name."))
        return
    counter = 1
    while os.path.exists(new_file_path):
        new_file_name = f"AAAWARNING_REPEATED_({counter}){base_name}.mp3"
        print(colortxt("Y", f"File name collision: {new_file_name} already exists."))
        if len(new_file_name) > 255:
            new_file_name = new_file_name[:255]
        new_file_path = os.path.join(songs_path, new_file_name)
        counter += 1

    try:
        os.rename(file_path, new_file_path)
        print(colortxt("B", f"Renamed {file_path} to {new_file_name}"))
    except Exception as e:
        print(colortxt("R", f"Error renaming {file_path}: {e}"))

def setup():
    if not os.path.exists(songs_path):
        print(colortxt("Y", "Songs directory not found, creating it..."))
        os.makedirs(songs_path)


def main():
    for file in os.listdir(songs_path):
        if file.lower().endswith(".mp3"):
            file_path = os.path.join(songs_path, file)
            metadata = read_metadata(file_path)
            if metadata:
                artist = metadata['artist']
                title = metadata['title']
                delete_metadata(file_path)
                if artist and title:
                    rename_file(file_path, artist, title)
                else:
                    print(colortxt("Y", f"Missing artist or title in {file_path}, skipping..."))
                    print(colortxt("Y", f"Artist: {artist}, Title: {title}"))
            else:
                print(colortxt("Y", f"Skipping {file_path} due to read error."))

if __name__ == "__main__":
    setup()
    main()
    input(colortxt("B", "Press Enter to exit..."))