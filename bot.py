import io
import os
import re
import sys
import feedparser
import mwclient
import requests
from dotenv import load_dotenv
from pathvalidate import sanitize_filename

load_dotenv()

WIKI_USER = os.environ['WIKI_USER']
WIKI_PASSWORD = os.environ['WIKI_PASSWORD']
CHANNEL_ID = "UCbRBrPjdAPQh0sdP33MFN7Q"
HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

escaped_trans = str.maketrans({
    '|': '—',
    '[': '(',
    ']': ')',
    '{': '(',
    '}': ')'
})

def is_short(video_id: str) -> bool:
	try:
		url = f"https://www.youtube.com/shorts/{video_id}"
		response = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=5)
		return "/shorts/" in response.url
	except requests.RequestException as e:
		print(e)
		sys.exit(1)

def get_thumbnail_bytes(video_id: str):
	resolutions = ['maxresdefault.jpg', 'sddefault.jpg', 'hqdefault.jpg']
	for res in resolutions:
		try:
			resp = requests.get(f"https://img.youtube.com/vi/{video_id}/{res}", headers=HEADERS, timeout=10)
			if resp.status_code == 200:
				return resp.content
		except requests.RequestException:
			continue
	return None

def clean_wiki_title(title: str) -> str:
	title = title.translate(escaped_trans)
	title = re.sub(pattern=r'[:#<>{}/\\?*]', repl='', string=title)
	return sanitize_filename(title, max_len=85).strip()

rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
try:
	response = requests.get(rss_url, timeout=10)
	response.raise_for_status()
	feed = feedparser.parse(response.content)
except requests.exceptions.RequestException as e:
	print(e)
	sys.exit(1)

if not feed.entries:
	sys.exit(0)

latest_videos = []
for entry in feed.entries:
	v_id = entry.yt_videoid
	if not is_short(v_id):
		clean_name = clean_wiki_title(entry.title)
		escaped_title = entry.title.translate(escaped_trans)
		latest_videos.append({
			'id': v_id,
			'filename': f"{clean_name}.jpg",
			'title': escaped_title
		})
	if len(latest_videos) == 10:
		break

if not latest_videos:
	sys.exit(0)

site = mwclient.Site('toster.fandom.com', path='/ru/', clients_useragent='YoutubeUpdater/1.0 (https://toster.fandom.com/ru/wiki/User:TONNY618; spdodle@gmail.com)')

template_page = site.pages['Template:LastVideo']
header_match = re.search(
	pattern=r'Последнее видео на канале.*?watch\?v=([\w-]+)',
	string=template_page.text(),
	flags=re.DOTALL
)

if (header_match.group(1) if header_match else None) == latest_videos[0]['id']:
	sys.exit(0)

site.login(WIKI_USER, WIKI_PASSWORD)

new_video = latest_videos[0]

gallery_lines = []
for vid in reversed(latest_videos[:3]):
	image_page = site.images[vid['filename']]
	if not image_page.exists:
		img_data = get_thumbnail_bytes(vid['id'])
		if img_data:
			site.upload(
				file=io.BytesIO(img_data), # type: ignore
				filename=vid['filename'],
				ignore=True
			)
	gallery_lines.insert(0, f"Файл:{vid['filename']}|[https://www.youtube.com/watch?v={vid['id']} {vid['title']}]")

gallery_content = "\n".join(gallery_lines)

template_content = f"""<includeonly>{{|style="width:100%; margin-bottom:10px; border: solid 4px; border-color: #9f7a6a; color:#8e6e5d; background-color: #ffe9d6; text-align:center; overflow:hidden; border-radius: 30px;"
|-
|style="padding-left:10px; padding-right:10px; font-size:200%;" class="main-page-new-episode-box" |Последнее видео на канале Нейро-шоу Тостера:<br /><span style="background:linear-gradient(to right, #c63c28, #812a20); -webkit-background-clip:text !important; -webkit-text-fill-color:transparent;">[https://www.youtube.com/watch?v={new_video['id']} {new_video['title']}]</span>
|}}
<gallery type="slider" orientation="bottom">
{gallery_content}
</gallery></includeonly><noinclude>
Шаблон обновляется ботом
</noinclude>"""

template_page.save(template_content, summary="Новое видео")

if len(latest_videos) > 3:
	for vid in latest_videos[3:]:
		old_image = site.images[vid['filename']]
		if old_image.exists:
			old_image.delete(reason="Ротация превью")