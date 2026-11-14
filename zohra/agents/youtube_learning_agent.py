"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — YOUTUBE LEARNING AGENT                       ║
║            YouTube Video Transcript Extraction & Segmenting          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import re
from typing import Dict, List, Any

logger = logging.getLogger("zohra.research.youtube")

class YouTubeLearningAgent:
    """
    Extracts transcripts from YouTube educational or trading videos
    and segments them into structured learning notes.
    """
    def extract_transcript(self, video_url: str) -> Dict[str, Any]:
        video_id = self._extract_video_id(video_url)
        if not video_id:
            return {"error": f"Invalid YouTube URL: {video_url}"}
            
        transcript_text = ""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            logger.info(f"Fetching transcript for video ID: {video_id}")
            
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            chunks = []
            for item in transcript_list:
                text = item.get("text", "")
                chunks.append(text)
            transcript_text = " ".join(chunks)
        except ImportError:
            logger.warning("youtube-transcript-api is not installed.")
            return {
                "error": "youtube-transcript-api library not installed. Cannot fetch transcripts.",
                "video_id": video_id,
                "video_url": video_url
            }
        except Exception as e:
            logger.error(f"Failed to fetch YouTube transcript: {e}")
            return {
                "error": f"Could not retrieve transcript: {str(e)}",
                "video_id": video_id,
                "video_url": video_url
            }

        # Segment the transcript into mock chapters based on pauses or keywords
        chapters = self._segment_transcript(transcript_text)
        
        return {
            "video_id": video_id,
            "video_url": video_url,
            "full_transcript": transcript_text,
            "chapters": chapters
        }

    def _extract_video_id(self, url: str) -> str:
        """Extracts the 11-character YouTube video ID using regex."""
        pattern = r"(?:v=|\/)([a-zA-Z0-9_-]{11})(?:\?|&|$)"
        match = re.search(pattern, url)
        return match.group(1) if match else ""

    def _segment_transcript(self, text: str) -> List[Dict[str, str]]:
        """Splits the transcript into logical paragraphs/chapters for easier reading."""
        words = text.split()
        chunk_size = 150
        chapters = []
        
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i+chunk_size]
            chapter_text = " ".join(chunk_words)
            chapters.append({
                "chapter_title": f"Segment {len(chapters) + 1}",
                "content": chapter_text
            })
            
        return chapters

# Singleton
youtube_learning_agent = YouTubeLearningAgent()
