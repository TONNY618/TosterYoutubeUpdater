import os
import re
import feedparser
import mwclient

WIKI_USER = os.environ.get('WIKI_USER')
WIKI_PASSWORD = os.environ.get('WIKI_PASSWORD')
CHANNEL_ID = "UCbRBrPjdAPQh0sdP33MFN7Q"

rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
feed = feedparser.parse(rss_url)

if not feed.entries:
	exit(0)

latest_video = feed.entries[0]
video_id = latest_video.yt_videoid
video_title = latest_video.title

site = mwclient.Site('toster.fandom.com', path='/')
site.login(WIKI_USER, WIKI_PASSWORD)

page = site.pages['Заглавная_страница']
content = page.text()

if video_id in content:
	exit(0)

updated_content = re.sub(r'watch\?v=[\w-]+', f'watch?v={video_id}', content)
page.save(updated_content, summary=f'Update: {video_title}')