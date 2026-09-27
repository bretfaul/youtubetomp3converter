YouTube -> MP3 Converter
 
Single-window, menu-driven layout:
    File menu        - choose/open download folder, exit
    Preferences menu - MP3 bitrate / sample rate
    Sign In menu     - AcoustID API key + matching toggle
    Options menu     - misc app behavior
 
Left panel:
    - Paste a YouTube link -> metadata is fetched automatically
    - Edit Title / Artist / Album / Year / Track / Genre
    - "Add Song to Queue" downloads it immediately (no separate
      Start button -- queuing IS starting)
    - Directory field controls where songs are saved
    - A small queue list shows Waiting / Downloading / Complete /
      Error songs (color-coded), capped at 25 pending at a time
 
Right panel:
    - Shows every MP3 already in the download folder
    - Click a row to load its tags into the left panel and edit them
      ("Add Song to Queue" becomes "Save Tags" while a row is selected)
 
Requirements:
    pip install yt-dlp mutagen pyacoustid
 
Also required:
    ffmpeg
 
Optional:
    fpcalc / Chromaprint
    AcoustID API key
"""
