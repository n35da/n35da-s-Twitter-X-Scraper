# Twitter / X Account Archiver

Archive a Twitter/X account's tweets, retweets, replies, and media to a self-contained offline viewer.

---

### Requirements
- **Python 3.10+**
- **gallery-dl**

```bash
pip install gallery-dl
```

---

### How to use

#### GUI:
```bash
python gui.py
```

1. Enter the target username (without @)
2. Optionally browse to a `cookies.txt` file for authenticated access
3. **NOT USING COOKIES.TXT WILL LIKELY RESULT IN SCRAPING NOT WORKING**
4. Click **Start Scraping**
5. When finished, click **Open Viewer**

#### Command Line

```bash
python archiver.py <username>
python archiver.py <username> --cookies cookies.txt
```

---

## Getting Cookies

Twitter rate-limits unauthenticated scraping heavily. Cookies let gallery-dl scrape as your logged-in account, giving far better results and access to more content.

### Export a cookies.txt file

# DO NOT GIVE ANYONE YOUR COOKIES.txt
1. Log into x.com in Chrome or Firefox
2. Install the **"Get cookies.txt LOCALLY"** extension:
   - [Chrome Web Store](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)
3. Navigate to x.com, click the extension icon, choose **Export**, then save as `cookies.txt`
4. In the GUI, click **Browse cookies.txt…** and select the file
   or on the command line: `--cookies cookies.txt`

# DO NOT GIVE ANYONE YOUR COOKIES.txt

---


## CLI Options

```
python archiver.py <username> [options]

Options:
  --cookies FILE    Netscape cookies.txt for authenticated scraping
  --no-retweets     Skip retweets
  --no-replies      Skip the with_replies tab
  --no-quoted       Skip quoted tweets
  --no-videos       Skip video files
  --out DIR         Output directory (default: ./twitter_archive/<username>)
```

---

## Output Structure

```
twitter_archive/
└── <username>/
    ├── viewer.html          ← Open this in your browser
    ├── archive.json         ← All tweet metadata in one file
    ├── gallery-dl-config.json
    └── media/
        ├── 1234567_1.jpg
        ├── 1234567_2.jpg
        ├── 9876543_1.mp4
        └── ...
```

Open `viewer.html` directly in any modern browser — no server required.

---

## Building a Standalone .exe

```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name TwitterArchiver --add-data "viewer.html;." gui.py
```

The `.exe` will be in the `dist/` folder. The `viewer.html` template is bundled inside it.

---

Currently only captures:

- Text tweets
- Media tweets (Images, Videos, Gifs)
- Retweets
- Replies
- profile pictures



Does not capture:
- poles
- threads
- likes
