import io
import os
import re
import sys
import time

import feedparser
import mwclient
import requests
from dotenv import load_dotenv
from pathvalidate import sanitize_filename

load_dotenv()

WIKI_USER = os.environ['WIKI_USER']
WIKI_PASSWORD = os.environ['WIKI_PASSWORD']
CHANNEL_ID = "UCbRBrPjdAPQh0sdP33MFN7Q"
PLAYLIST_ID = "UU" + CHANNEL_ID[2:] if CHANNEL_ID.startswith("UC") else CHANNEL_ID
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
WIKI_CHAR_MAP = str.maketrans({
	'|': '—',
	'[': '(',
	']': ')',
	'{': '(',
	'}': ')'
})

def is_short(video_id: str, max_retries: int = 3, backoff_factor: float = 1.5) -> bool:
	url = f"https://www.youtube.com/shorts/{video_id}"
	last_error = None
	
	for attempt in range(max_retries):
		try:
			with requests.get(url, headers=HEADERS, allow_redirects=True, timeout=5, stream=True) as response:
				if response.ok:
					return "/shorts/" in response.url
				
				if response.status_code == 429 or response.status_code >= 500:
					time.sleep(backoff_factor * (2 ** attempt))
					continue
				
				raise RuntimeError(f"HTTP {response.status_code}")
		except requests.RequestException as e:
			last_error = e
			time.sleep(backoff_factor * (2 ** attempt))
		
	raise RuntimeError(f"Failed to check video {video_id} after {max_retries} attempts: {last_error}")

def get_thumbnail_bytes(video_id: str):
	thumbnail_variants = ['maxresdefault.jpg', 'sddefault.jpg', 'hqdefault.jpg']
	for resolution in thumbnail_variants:
		try:
			response = requests.get(f"https://img.youtube.com/vi/{video_id}/{resolution}", headers=HEADERS, timeout=10)
			if response.status_code == 200:
				return response.content
		except requests.RequestException:
			continue
	return None

def clean_wiki_title(title: str) -> str:
	title = title.translate(WIKI_CHAR_MAP)
	title = re.sub(pattern=r'[:#<>{}/\\?*]', repl='', string=title)
	return sanitize_filename(title, max_len=85).strip()

def fetch_youtube_feed(max_retries: int = 3, backoff_factor: float = 1.5):
	rss_urls = [
		f"https://www.youtube.com/feeds/videos.xml?playlist_id={PLAYLIST_ID}",
		f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}",
	]
	
	for attempt in range(max_retries):
		for url in rss_urls:
			try:
				feed_response = requests.get(url, headers=HEADERS, timeout=10)
				feed_response.raise_for_status()
				feed = feedparser.parse(feed_response.content)
				if feed.entries:
					return feed
			except requests.RequestException:
				pass
		
		time.sleep(backoff_factor * (2 ** attempt))
	
	return None

def main():
	feed = fetch_youtube_feed()
	if not feed:
		print("::warning title=YouTube Feed Unavailable::Failed to fetch RSS feed (YouTube returned 404/error). Skipping iteration.")
		sys.exit(0)
	
	latest_videos = []
	try:
		for entry in feed.entries:
			video_id = entry.yt_videoid
			if not is_short(video_id):
				safe_name = clean_wiki_title(entry.title)
				escaped_title = entry.title.translate(WIKI_CHAR_MAP)
				latest_videos.append({
					'id': video_id,
					'filename': f"{safe_name} {video_id}.jpg" if safe_name else f"{video_id}.jpg",
					'title': escaped_title
				})
			if len(latest_videos) == 10:
				break
	except RuntimeError as e:
		sys.exit(f"::error title=YouTube Check Failed::{e}")
	
	if not latest_videos:
		sys.exit(0)
	
	site = mwclient.Site('toster.fandom.com', path='/ru/', clients_useragent='YoutubeUpdater/1.0 (https://toster.fandom.com/ru/wiki/User:TONNY618; spdodle@gmail.com)')
	
	template_page = site.pages['Template:LastVideo']
	header_match = re.search(
		pattern=r'Последнее видео на канале.*?watch\?v=([\w-]+)',
		string=template_page.text(),
		flags=re.DOTALL
	)
	
	new_video = latest_videos[0]
	if (header_match.group(1) if header_match else None) == new_video['id']:
		sys.exit(0)
	
	site.login(WIKI_USER, WIKI_PASSWORD)
	
	gallery_lines = []
	for video in reversed(latest_videos[:3]): # Uploading in reverse order (from oldest to newest) so that Fandom has the correct chronology.
		image_page = site.images[video['filename']]
		if not image_page.exists:
			img_data = get_thumbnail_bytes(video['id'])
			if img_data:
				site.upload(
					file=io.BytesIO(img_data), # type: ignore
					filename=video['filename'],
					ignore=True
				)
		gallery_lines.insert(0, f"Файл:{video['filename']}|[https://www.youtube.com/watch?v={video['id']} {video['title']}]")
	
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
		for video in latest_videos[3:]:
			old_image = site.images[video['filename']]
			if old_image.exists:
				old_image.delete(reason="Ротация превью")

if __name__ == "__main__":
	main()