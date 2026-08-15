from googleapiclient.discovery import build
import re
from core.config import settings

def extract_video_id(url: str) -> str:
    # Handle various YouTube URL formats
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    
    # Handle youtu.be format
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[1][:11]
        
    raise ValueError("Invalid YouTube URL")

class YouTubeService:
    def __init__(self):
        if not settings.YOUTUBE_API_KEY:
            raise ValueError("YOUTUBE_API_KEY is not set")
        self.youtube = build('youtube', 'v3', developerKey=settings.YOUTUBE_API_KEY)

    def get_video_metadata(self, video_id: str) -> dict:
        request = self.youtube.videos().list(
            part="snippet,statistics",
            id=video_id
        )
        response = request.execute()
        
        if not response.get('items'):
            raise ValueError("Video not found")
            
        item = response['items'][0]
        snippet = item['snippet']
        statistics = item['statistics']
        
        return {
            'youtube_id': video_id,
            'title': snippet.get('title'),
            'channel': snippet.get('channelTitle'),
            'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url'),
            'comment_count': int(statistics.get('commentCount', 0))
        }

    def get_comments(self, video_id: str, max_results: int = 100) -> list:
        comments = []
        try:
            request = self.youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=min(100, max_results),
                textFormat="plainText"
            )
            
            while request and len(comments) < max_results:
                response = request.execute()
                
                for item in response.get('items', []):
                    top_level = item['snippet']['topLevelComment']
                    comments.append({
                        'youtube_id': top_level['id'],
                        'parent_id': None,
                        'author_name': top_level['snippet'].get('authorDisplayName'),
                        'text': top_level['snippet'].get('textDisplay'),
                        'published_at': top_level['snippet'].get('publishedAt'),
                        'like_count': top_level['snippet'].get('likeCount', 0),
                        'is_reply': False
                    })
                    
                    if len(comments) >= max_results:
                        break
                        
                    # Handle replies if available
                    if 'replies' in item:
                        for reply in item['replies'].get('comments', []):
                            comments.append({
                                'youtube_id': reply['id'],
                                'parent_id': top_level['id'],
                                'author_name': reply['snippet'].get('authorDisplayName'),
                                'text': reply['snippet'].get('textDisplay'),
                                'published_at': reply['snippet'].get('publishedAt'),
                                'like_count': reply['snippet'].get('likeCount', 0),
                                'is_reply': True
                            })
                            if len(comments) >= max_results:
                                break
                                
                if len(comments) < max_results and 'nextPageToken' in response:
                    request = self.youtube.commentThreads().list(
                        part="snippet,replies",
                        videoId=video_id,
                        pageToken=response['nextPageToken'],
                        maxResults=min(100, max_results - len(comments)),
                        textFormat="plainText"
                    )
                else:
                    break
        except Exception as e:
            print(f"Error fetching comments: {e}")
            
        return comments
