import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import sys

from adapters import store
from adapters.content import ContentExtractionError
from adapters.media import YouTubeTranscript, _caption_text, _youtube_video_id
from adapters.podcast import _Document, ResolvedPodcastEpisode, resolve_podcast_episode
from adapters.url_fetch import FetchedUrlContent
from core.models import OriginalType, SourceType
from services import agent_service


class _FakeContentGraph:
    def invoke(self, state: dict) -> dict:
        article_id = store.save_article(state["article"])
        store.link_input_asset_to_article(state["input_asset"].id, article_id)
        return {"persisted_article_id": article_id, "chunks": []}


class _Caption:
    def __init__(self, text: str) -> None:
        self.text = text


class _TranscriptClient:
    def fetch(self, video_id: str) -> list[_Caption]:
        return [_Caption("First caption."), _Caption("Second caption.")]


class MediaIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_sqlite_path = store.SQLITE_PATH
        store.SQLITE_PATH = Path(self.temp_dir.name) / "test.db"

    def tearDown(self) -> None:
        store.SQLITE_PATH = self.previous_sqlite_path
        self.temp_dir.cleanup()

    def test_youtube_id_accepts_common_video_urls(self) -> None:
        self.assertEqual(_youtube_video_id("https://youtu.be/AbCdEf12345?t=10"), "AbCdEf12345")
        self.assertEqual(_youtube_video_id("https://www.youtube.com/shorts/AbCdEf12345"), "AbCdEf12345")
        with self.assertRaises(ContentExtractionError):
            _youtube_video_id("https://example.com/watch?v=AbCdEf12345")

    def test_youtube_caption_objects_are_normalized(self) -> None:
        module = ModuleType("youtube_transcript_api")
        module.YouTubeTranscriptApi = _TranscriptClient
        with patch.dict(sys.modules, {"youtube_transcript_api": module}):
            self.assertEqual(
                _caption_text("AbCdEf12345"), "First caption.\n\nSecond caption."
            )

    @patch("adapters.podcast._fetch_document")
    def test_resolver_prefers_a_feed_transcript_before_audio(self, fetch_document) -> None:
        feed = b"""<?xml version='1.0'?>
        <rss xmlns:podcast='https://podcastindex.org/namespace/1.0'><channel>
          <title>Example show</title><link>https://example.com/show</link><language>en</language>
          <item><title>Episode 42</title><guid>https://example.com/episodes/42</guid>
            <enclosure url='https://cdn.example.com/42.mp3' type='audio/mpeg'/>
            <podcast:transcript url='https://example.com/42.vtt' type='text/vtt'/>
          </item>
        </channel></rss>"""
        fetch_document.return_value = _Document(
            url="https://example.com/feed.xml",
            content_type="application/rss+xml",
            content=feed,
        )

        resolved = resolve_podcast_episode("https://example.com/feed.xml")

        self.assertEqual(resolved.title, "Episode 42")
        self.assertEqual(resolved.transcript_url, "https://example.com/42.vtt")
        self.assertEqual(resolved.audio_url, "https://cdn.example.com/42.mp3")

    @patch("adapters.podcast._spotify_metadata", return_value=("Episode title", "Spotify", "https://open.spotify.com"))
    @patch("adapters.podcast._discovered_feeds", return_value=[])
    @patch("adapters.podcast._fetch_document")
    def test_spotify_preview_audio_is_never_used(self, fetch_document, discovered_feed, spotify_metadata) -> None:
        fetch_document.return_value = _Document(
            url="https://open.spotify.com/episode/episode-1",
            content_type="text/html",
            content=b"<html><head><title>Episode title - Example Show | Podcast on Spotify</title><meta property='og:audio' content='https://p.scdn.co/mp3-preview/preview.mp3'></head></html>",
        )

        with self.assertRaises(ContentExtractionError):
            resolve_podcast_episode("https://open.spotify.com/episode/episode-1")

    @patch("services.agent_service.qualify_source", side_effect=lambda source: source)
    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    @patch("services.agent_service.fetch_youtube_transcript")
    def test_youtube_captions_become_text_content(self, fetch_transcript, build_graph, qualify_source) -> None:
        fetch_transcript.return_value = YouTubeTranscript(
            video_url="https://www.youtube.com/watch?v=AbCdEf12345",
            title="Video title",
            channel_name="A channel",
            channel_url="https://www.youtube.com/@channel",
            text="First caption.\n\nSecond caption.",
        )

        result = agent_service.add_youtube_video("https://youtu.be/AbCdEf12345")
        detail = store.get_article_detail(result["article"]["id"])

        self.assertEqual(detail["content"], "First caption.\n\nSecond caption.")
        self.assertEqual(detail["url"], "https://www.youtube.com/watch?v=AbCdEf12345")
        self.assertEqual(detail["source"]["type"], SourceType.VIDEO.value)
        self.assertEqual(detail["input_assets"][0]["original_type"], OriginalType.TEXT.value)

    @patch("services.agent_service.qualify_source", side_effect=lambda source: source)
    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    def test_podcast_transcript_becomes_text_content(self, build_graph, qualify_source) -> None:
        result = agent_service.add_podcast_episode(
            url="https://podcasts.example.com/episodes/42",
            title="Episode 42",
            transcript="Welcome to the episode.\n\nWe discuss retrieval.",
        )
        detail = store.get_article_detail(result["article"]["id"])

        self.assertEqual(detail["content"], "Welcome to the episode.\n\nWe discuss retrieval.")
        self.assertEqual(detail["url"], "https://podcasts.example.com/episodes/42")
        self.assertEqual(detail["source"]["type"], SourceType.PODCAST.value)
        self.assertEqual(detail["input_assets"][0]["raw_text"], "Welcome to the episode.\n\nWe discuss retrieval.")

    @patch("services.agent_service.qualify_source", side_effect=lambda source: source)
    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    @patch("services.agent_service.fetch_url_content")
    def test_podcast_can_fetch_a_transcript_page(self, fetch_url_content, build_graph, qualify_source) -> None:
        fetch_url_content.return_value = FetchedUrlContent(
            requested_url="https://example.com/transcript",
            final_url="https://example.com/transcript",
            filename="transcript.html",
            mime_type="text/html",
            original_type=OriginalType.TEXT,
            title="Transcript title",
            text="A readable transcript.",
            content=b"<html>A readable transcript.</html>",
        )
        result = agent_service.add_podcast_episode(
            url="https://podcasts.example.com/episodes/43",
            transcript_url="https://example.com/transcript",
        )

        detail = store.get_article_detail(result["article"]["id"])
        self.assertEqual(detail["title"], "Transcript title")
        self.assertEqual(detail["content"], "A readable transcript.")

    @patch("services.agent_service.qualify_source", side_effect=lambda source: source)
    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    @patch("services.agent_service.fetch_podcast_transcript", return_value="Publisher transcript.")
    @patch("services.agent_service.resolve_podcast_episode")
    def test_podcast_url_uses_a_discovered_publisher_transcript(
        self, resolve, fetch_transcript, build_graph, qualify_source
    ) -> None:
        resolve.return_value = ResolvedPodcastEpisode(
            episode_url="https://open.spotify.com/episode/episode-1",
            title="Episode one",
            publisher_name="Example show",
            publisher_url="https://example.com/show",
            transcript_url="https://example.com/episode-1.vtt",
        )

        result = agent_service.add_podcast_episode(
            url="https://open.spotify.com/episode/episode-1"
        )
        detail = store.get_article_detail(result["article"]["id"])

        fetch_transcript.assert_called_once_with("https://example.com/episode-1.vtt")
        self.assertEqual(detail["content"], "Publisher transcript.")
        self.assertEqual(detail["url"], "https://open.spotify.com/episode/episode-1")
        self.assertEqual(detail["source"]["name"], "Example show")

    @patch("services.agent_service.qualify_source", side_effect=lambda source: source)
    @patch("services.agent_service.build_content_ingest_graph", return_value=_FakeContentGraph())
    @patch("services.agent_service.transcribe_podcast_audio", return_value="Locally transcribed audio.")
    @patch("services.agent_service.resolve_podcast_episode")
    def test_podcast_url_transcribes_a_public_enclosure(
        self, resolve, transcribe, build_graph, qualify_source
    ) -> None:
        resolve.return_value = ResolvedPodcastEpisode(
            episode_url="https://podcasts.apple.com/episode-1",
            title="Episode one",
            publisher_name="Example show",
            publisher_url="https://example.com/show",
            audio_url="https://cdn.example.com/episode-1.mp3",
            language="en",
        )

        result = agent_service.add_podcast_episode(
            url="https://podcasts.apple.com/episode-1"
        )
        detail = store.get_article_detail(result["article"]["id"])

        transcribe.assert_called_once_with("https://cdn.example.com/episode-1.mp3", language="en")
        self.assertEqual(detail["content"], "Locally transcribed audio.")

    def test_podcast_rejects_both_manual_transcript_inputs(self) -> None:
        with self.assertRaises(ContentExtractionError):
            agent_service.add_podcast_episode(
                url="https://podcasts.example.com/episodes/42",
                transcript="A transcript.",
                transcript_url="https://example.com/transcript",
            )


if __name__ == "__main__":
    unittest.main()
