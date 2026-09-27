Synthetic 3-second fixtures (no third-party media). Generated with FFmpeg 7.1:

```sh
ffmpeg -f lavfi -i testsrc2=size=32x32:rate=10 -t 3 -an -c:v libx264 -pix_fmt yuv420p -g 10 -bf 2 -movflags +dash+frag_keyframe+empty_moov+default_base_moof+global_sidx video.mp4
ffmpeg -f lavfi -i sine=frequency=440:sample_rate=22050 -t 3 -vn -c:a aac -b:a 16k -ac 1 -frag_duration 1000000 -movflags +dash+empty_moov+default_base_moof+global_sidx audio.mp4
```

Used to exercise real MP4 initialization, SIDX offsets, fragment extraction,
keyframe seeking and B-frame composition offsets without external network access.
