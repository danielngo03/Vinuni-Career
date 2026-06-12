import unittest

from backend.src.services.youtube_rag_pipeline import build_chunks, detect_source_type


class YoutubeRagPipelineTests(unittest.TestCase):
    def test_detects_video_and_playlist_urls(self):
        self.assertEqual(detect_source_type("https://www.youtube.com/watch?v=abc123"), "video")
        self.assertEqual(detect_source_type("https://www.youtube.com/playlist?list=PL123"), "playlist")

    def test_build_chunks_preserves_timestamp_metadata(self):
        cleaned = {
            "video": {
                "id": "video_1",
                "title": "Lecture",
                "url": "https://www.youtube.com/watch?v=video_1",
                "channel": "MIT OpenCourseWare",
                "language": "en",
            },
            "metadata": {
                "category": "Biology & Chemistry",
                "course_title": "Chemistry Principles",
                "course_url": "https://www.youtube.com/playlist?list=PL123",
            },
            "segments": [
                {"index": 0, "start": 10.0, "end": 12.0, "text": "alpha beta gamma delta"},
                {"index": 1, "start": 12.0, "end": 15.0, "text": "epsilon zeta eta theta"},
            ],
        }

        chunks = build_chunks(cleaned, chunk_size_words=5, overlap_words=2)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["metadata"]["start_time"], 10.0)
        self.assertEqual(chunks[0]["metadata"]["end_time"], 15.0)
        self.assertEqual(chunks[0]["metadata"]["start_segment_index"], 0)
        self.assertEqual(chunks[0]["metadata"]["end_segment_index"], 1)
        self.assertIn("t=10", chunks[0]["metadata"]["timestamp_url"])


if __name__ == "__main__":
    unittest.main()
