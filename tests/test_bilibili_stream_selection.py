import unittest
from unittest.mock import patch

from bilibili_api import video

# ffvideo initializes its legacy FIFO on import. Avoid touching the shared
# /tmp path in tests and provide the missing API when tests run on Windows.
with patch('os.path.exists', return_value=False), patch('os.mkfifo', create=True):
    from ffvideo.bv import (
        build_dash_mux_command,
        build_single_stream_mux_command,
        select_preferred_streams,
    )


class FakeDownloadURLDataDetecter:
    def __init__(self, streams):
        self.streams = streams

    def detect(self, **_kwargs):
        return self.streams

    def check_video_and_audio_stream(self):
        return True


class BilibiliStreamSelectionTest(unittest.TestCase):
    def setUp(self):
        self.unknown_codec_video = video.VideoStreamDownloadURL(
            url='https://example.test/hevc.m4s',
            video_quality=video.VideoQuality._480P,
            video_codecs=None,
        )
        self.avc_video = video.VideoStreamDownloadURL(
            url='https://example.test/avc.m4s',
            video_quality=video.VideoQuality._480P,
            video_codecs=video.VideoCodecs.AVC,
        )
        self.audio = video.AudioStreamDownloadURL(
            url='https://example.test/audio.m4s',
            audio_quality=video.AudioQuality._192K,
        )

    @patch('ffvideo.bv.get_bilibili_max_quality', return_value=video.VideoQuality._720P)
    def test_ignores_unknown_codec_and_selects_avc(self, _get_max_quality):
        detecter = FakeDownloadURLDataDetecter([
            self.unknown_codec_video,
            self.avc_video,
            self.audio,
        ])

        selected_video, selected_audio, error = select_preferred_streams(detecter, 'test')

        self.assertIs(selected_video, self.avc_video)
        self.assertIs(selected_audio, self.audio)
        self.assertIsNone(error)

    @patch('ffvideo.bv.get_bilibili_max_quality', return_value=video.VideoQuality._720P)
    def test_reports_no_avc_when_only_unknown_codec_exists(self, _get_max_quality):
        detecter = FakeDownloadURLDataDetecter([
            self.unknown_codec_video,
            self.audio,
        ])

        selected_video, selected_audio, error = select_preferred_streams(detecter, 'test')

        self.assertIsNone(selected_video)
        self.assertIsNone(selected_audio)
        self.assertEqual(error, 'no_avc_stream')


class BilibiliMuxCommandTest(unittest.TestCase):
    def test_dash_streams_are_remuxed_without_video_transcoding(self):
        command = build_dash_mux_command(
            '/tmp/video.m4s',
            '/tmp/audio.m4s',
            '/tmp/output.flv',
        )

        self.assertEqual(command[command.index('-c:v') + 1], 'copy')
        self.assertEqual(command[command.index('-c:a') + 1], 'copy')
        self.assertNotIn('libx264', command)
        self.assertNotIn('-vf', command)
        self.assertIn('no_duration_filesize', command)

    def test_remote_seek_remains_on_zero_transcode_path(self):
        command = build_dash_mux_command(
            'https://example.test/video.m4s',
            'https://example.test/audio.m4s',
            '/tmp/output.flv',
            start_ms=30000,
            remote_inputs=True,
        )

        self.assertEqual(command.count('-ss'), 2)
        self.assertEqual(command.count('-headers'), 2)
        self.assertEqual(command[command.index('-c:v') + 1], 'copy')
        self.assertNotIn('libx264', command)

    def test_single_stream_is_remuxed_without_transcoding(self):
        command = build_single_stream_mux_command(
            'https://example.test/combined.flv',
            '/tmp/output.flv',
            start_ms=5000,
        )

        self.assertEqual(command[command.index('-c') + 1], 'copy')
        self.assertNotIn('libx264', command)


if __name__ == '__main__':
    unittest.main()
