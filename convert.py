import json
from datetime import datetime
import os
import zipfile
import uuid
import hashlib
from pathlib import Path
import platform
import re
import shutil
from typing import Dict, Tuple, Any, Optional
from tqdm import tqdm
from rich.console import Console

console = Console()

class DayOneJSONEncoder(json.JSONEncoder):
    def encode(self, obj):
        return super().encode(obj).replace('dayone-moment://', 'dayone-moment:\\/\\/')

    def iterencode(self, obj, _one_shot=False):
        for chunk in super().iterencode(obj, _one_shot):
            yield chunk.replace('dayone-moment://', 'dayone-moment:\\/\\/')

class TwitterToDayOne:
    def __init__(self, archive_path: Path):
        self.archive_path = Path(archive_path)
        self.tweets = []
        self.media_path = self.archive_path / 'data' / 'tweets_media'
        self.temp_dir = Path('temp_export')
        self.photos_dir = self.temp_dir / 'photos'
        self.videos_dir = self.temp_dir / 'videos'
        self.media_errors = []
    
    def load_twitter_data(self):
        """Load tweets from Twitter archive's tweets.js"""
        tweets_file = self.archive_path / 'data' / 'tweets.js'
        
        with open(tweets_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # Remove the "window.YTD.tweets.part0 = " prefix
            json_str = re.sub(r'^window.YTD.tweets.part0\s*=\s*', '', content.strip())
            self.tweets = json.loads(json_str)
            console.print(f"[green]Loaded {len(self.tweets)} tweets from archive[/green]")
    
    def find_media_file(self, media_item: Dict[str, Any]) -> Optional[Path]:
        """Find the correct media file in the archive"""
        media_url = media_item['media_url_https']
        tweet_id = media_item.get('id_str', '')
        
        # Try different possible filenames
        possible_names = [
            # Standard Twitter format: tweet_id-media_id.ext
            f"{tweet_id}-{media_url.split('/')[-1]}",
            # Just the media ID
            media_url.split('/')[-1],
            # Try without file extension
            f"{tweet_id}-{media_url.split('/')[-1].split('.')[0]}.*"
        ]
        
        for name in possible_names:
            # Handle wildcard search
            if '*' in name:
                matches = list(self.media_path.glob(name))
                if matches:
                    return matches[0]
            else:
                path = self.media_path / name
                if path.exists():
                    return path
        
        return None
    
    def process_media(self, media_item: Dict[str, Any], tweet_date: datetime) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Process a media item and return its DayOne metadata and moment URL"""
        local_media_path = self.find_media_file(media_item)
        
        if not local_media_path:
            error_msg = (
                f"Media file not found for tweet {media_item.get('id_str', 'unknown')}: "
                f"{media_item['media_url_https']}"
            )
            self.media_errors.append(error_msg)
            console.print(f"[yellow]Warning:[/yellow] {error_msg}")
            return None, None
        
        # Calculate MD5 first since we'll use it for both the filename and metadata
        with open(local_media_path, 'rb') as f:
            media_content = f.read()
            media_md5 = hashlib.md5(media_content).hexdigest()
        
        is_video = media_item['type'] == 'video'
        media_metadata = {
            "identifier": media_md5,  # Use MD5 as identifier instead of UUID
            "date": tweet_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "mp4" if is_video else "jpg",
            "md5": media_md5,
        }
        
        # Only add dimensions if they exist
        height = media_item.get('sizes', {}).get('large', {}).get('h')
        width = media_item.get('sizes', {}).get('large', {}).get('w')
        if height and width:
            media_metadata["height"] = int(height)
            media_metadata["width"] = int(width)
        
        # Copy media file to appropriate temp directory with MD5 as filename
        if is_video:
            dest_path = self.videos_dir / f"{media_md5}.mp4"
        else:
            dest_path = self.photos_dir / f"{media_md5}.jpg"
            
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_media_path, dest_path)
        
        # Create the moment URL for the entry text using MD5
        if is_video:
            moment_url = "![](dayone-moment:/video/" + media_md5 + ")"
        else:
            moment_url = "![](dayone-moment://" + media_md5 + ")"
        
        return media_metadata, moment_url
    
    def convert_tweet_to_entry(self, tweet_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a single tweet to DayOne entry format"""
        tweet = tweet_data['tweet']
        tweet_date = datetime.strptime(tweet['created_at'], '%a %b %d %H:%M:%S %z %Y')
        
        entry = {
            "creationDate": tweet_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "uuid": uuid.uuid4().hex.upper(),
            "starred": False,
            "text": tweet['full_text'],
            "tags": [],
            "photos": [],
            "videos": []
        }
        
        # Process media if present
        if 'extended_entities' in tweet and 'media' in tweet['extended_entities']:
            text_parts = [entry['text']]
            photos = []
            videos = []
            
            for idx, media in enumerate(tweet['extended_entities']['media']):
                media['order'] = idx
                # Add the tweet ID to the media item
                media['id_str'] = tweet.get('id_str', '')
                media_metadata, moment_url = self.process_media(media, tweet_date)
                
                if media_metadata:
                    if media_metadata['type'] == 'mp4':
                        videos.append(media_metadata)
                    else:
                        photos.append(media_metadata)
                    
                    # Add newlines before and after moment URL
                    text_parts.append(moment_url)
            
            if photos:
                entry['photos'] = photos
            if videos:
                entry['videos'] = videos
            
            # Join with double newlines
            entry['text'] = '\n\n'.join(text_parts)
        
        # Add hashtags as tags
        if 'entities' in tweet and 'hashtags' in tweet['entities']:
            entry['tags'].extend([tag['text'] for tag in tweet['entities']['hashtags']])
        
        return entry
    
    def create_export_zip(self, output_path: Path):
        """Create DayOne-compatible ZIP archive"""
        output_path = Path(output_path)
        self.media_errors = []  # Reset media errors
        
        # Create temporary directories
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.photos_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Convert all tweets
            entries = []
            with tqdm(self.tweets, desc="Converting tweets") as pbar:
                for tweet_data in pbar:
                    entry = self.convert_tweet_to_entry(tweet_data)
                    entries.append(entry)
            
            # Create journal JSON
            journal_data = {
                'metadata': {
                    'version': '1.0'
                },
                'entries': entries
            }
            
            # Get the filename from the output path (without .zip extension)
            json_filename = output_path.stem + '.json'
            json_path = self.temp_dir / json_filename
            
            # Write JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(journal_data, f, indent=2, cls=DayOneJSONEncoder)
            
            # Create ZIP archive
            console.print(f"\nCreating ZIP archive at {output_path}...")
            with zipfile.ZipFile(output_path, 'w') as export_zip:
                # Add JSON file with same name as zip (but .json extension)
                export_zip.write(json_path, json_filename)
                
                # Add photos
                for photo in self.photos_dir.glob('*'):
                    export_zip.write(photo, f'photos/{photo.name}')
                
                # Add videos
                for video in self.videos_dir.glob('*'):
                    export_zip.write(video, f'videos/{video.name}')
            
            # Report any media errors
            if self.media_errors:
                console.print("\n[yellow]Warning: Some media files were not found:[/yellow]")
                for error in self.media_errors:
                    console.print(f"  - {error}")
            
            console.print("\n[green]Export completed successfully![/green]")
            
        finally:
            # Cleanup temporary files
            self._cleanup_temp_dir()
    
    def _cleanup_temp_dir(self):
        """Remove temporary directory and its contents"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)