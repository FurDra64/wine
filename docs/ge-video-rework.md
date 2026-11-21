# GE video patchset migration

`ge-video-rework` follows the complete Wine overlay, including
`valve-winegstreamer` (Fossilize rb-tree indexes) and `valve-misc-6` (asynchronous
WM reader). Replay the series in order; the unpatched Wine sources are not the
pre-image of the GE patches.

## Porting decisions

- `0001` reuses the rb-tree cache and hash helpers from the applied Valve stack.
  The standalone helper move and legacy decoder/resampler/color conversion
  payload come from GE-Proton `26ac1ad59`; the converter demuxer comes from
  Valve Wine `3999811509e43cc178270f19212a4143eec1412d`. Direct HTTP/RTSP uses
  FFmpeg's URL path; only seekable byte streams use the converter fallback.
  Later patches preserve the native-read-callback checks needed before treating
  custom FFmpeg IO as a Wine byte stream.
- `0009` replaces the original Quartz flush function instead of adding a second
  definition. `0014` follows the WM reader and Quartz changes; `0018` retains
  `video_decoder_needs_stream_change()` and the two-argument transition helper.
- `0066` and `0102` register MP43/mp43 and MP42/mp42 as **input** types in both
  WMVideo factories and the shared decoder. Keep the output subtype order and
  the enumeration/negotiation tests. `0103` applies on the rebased reader chain.

## Verification

```sh
bash scripts/apply-patches.sh --check -W ge-video-rework  # 100 patchsets, 244 files
bash scripts/apply-patches.sh --check                    # 101 patchsets, 352 files
bash scripts/apply-patches.sh --list | grep -Fx ge-video-rework
```

For strict verification, use a disposable Git repo seeded with the Wine sources.
Apply the enabled predecessors, then for each of the 108 GE patches in sorted
order run `git apply --numstat`, `git apply --check`, and
`patch -Np1 --fuzz=0 --dry-run --batch` against the cumulative pre-image. Apply
with Git, stage the result, reverse with `git apply --index -R --whitespace=nowarn`,
and compare the tree ID to the original. Reapply and compare the result to the
first post-image before advancing to the next patch.

The target build uses an exported Wine tree with the complete series applied,
`autoreconf -f`, `./tools/make_requests`, and
`./configure --enable-archs=x86_64 --without-x --without-wayland`. At base
`018ec40e2be`, `valve-build` registers seven absent Makefiles (`dlls/audioses`,
`dlls/protontts`, `dlls/wineopenxr`, `programs/belauncher`, `programs/dotnetfx35`,
`programs/getminidump`, `programs/tabtip`); omit those registrations **only in the
build scratch tree** to check the media targets. `valve-audio/0003` also leaves a
conflict marker in `pulse.c`; it and the `pulse_timer_loop` return-type mismatch
predate GE. These are not reasons to change the GE patches or claim a full Wine
build.

Run explicit artifact targets, not bare source directories (which Make can
report as already up to date without compiling):

```sh
make -j8 dlls/winedmo/winedmo.so dlls/winedmo/x86_64-windows/winedmo.dll \
  dlls/wmvdecod/x86_64-windows/wmvdecod.dll dlls/wmadmod/x86_64-windows/wmadmod.dll \
  dlls/qasf/x86_64-windows/qasf.dll dlls/mfmediaengine/x86_64-windows/mfmediaengine.dll \
  dlls/mf/x86_64-windows/mf.dll dlls/mfreadwrite/x86_64-windows/mfreadwrite.dll \
  dlls/mfsrcsnk/x86_64-windows/mfsrcsnk.dll dlls/quartz/x86_64-windows/quartz.dll \
  dlls/wmvcore/x86_64-windows/wmvcore.dll \
  dlls/mf/tests/x86_64-windows/mf_test.exe \
  dlls/quartz/tests/x86_64-windows/quartz_test.exe
```

These targets linked with x86-64 MinGW and system FFmpeg. Use `nm` on
`winedmo.so` to confirm `fozdb_tag_head`, `discard_transcoded_streams`, and
`mediaconv_demuxer_open`; `readelf -d` confirms no GStreamer dependency. Linking
Wine's test binaries does not run the tests or validate playback in a game.

## Review follow-up: source parity and ownership test

Compare the 108 patch basenames with Proton `750f21ec35190c7a79165d592b019f6346f27c00`.
For the 51 nonidentical patch files, compare signed changed lines by target
path, then inspect the differing hunks at their cumulative pre/post images.
An exact forward/reverse replay alone does not prove source parity.

- **`0001`:** Restore negative-PTS clamping, DTS/PTS selection for DMO buffer
  time, and the Opus/Vorbis 16-bit fallback. Keep the rb-tree FFmpeg converter
  port. Local class names differ; the same registration GUIDs select winedmo
  factories. WMA uses the retained implementation with a matching export and
  three-argument caller.
- **`0002`:** Preserve upstream `5fc7c7958be` asynchronous read-error
  notification for virtual stream IDs. Select the queued error by ID without
  indexing the physical stream array. Keep the current allocator helper
  (`8946e6df7ed`) and EOS fallback. `93aa62fbee8` separately validates nonzero
  IMF stream IDs in `mfsrcsnk`.
- **`0004`, `0007`, `0009`:** Include ARGB32 in both vidreszr tables. Guard
  FFmpeg's custom IO cast by its read callback. Install Quartz flush logic by
  replacing the existing function. Reanchor `0009`'s discontinuity flag to
  the restored `0001` timestamps.
- **`0010`:** GE's `VFW_E_WRONG_STATE` differs from Wine `7c48881f4fe`, which
  releases the wait and asserts `VFW_E_NOT_COMMITTED` in the Windows comparison
  test. The HRESULTs are not equivalent.
- **`0014`–`0017`, `0061`:** Keep WM stream selection, qasf pacing and initial
  samples. `mediaconv_demuxer_close` handles custom AVIO cleanup and closes direct
  input with `avformat_close_input`. Logging moved to `unixlib.c`; the resolver's
  initial position is explicit in the revised object context.
- **`0028`, `0040`, `0043`, `0059`, `0078`, `0102`:** Carry the Shcore delay
  import, H.264 probe and display-FPS diagnostic, embedded test-sink interface,
  and MP42 registrations. `0078` relies on the earlier custom-IO callback guard.
- **`0006`, `0062` (progressive MP4), `0063`:** Remove the live GStreamer
  latency override while leaving adjacent app hacks unchanged. Restore the
  `.mp4` URLMon bypass for HTTP(S), not just Googlevideo. Drop only delivered
  audio history; caller references, timestamps and pending transform drain stay
  in place.

The ownership test is in `dlls/mfreadwrite/tests/mfplat.c`, at
`check_source_reader_sample_lifetime()`. Build and run it in the test runtime:

```sh
make dlls/mfreadwrite/x86_64-windows/mfreadwrite.dll \
  dlls/mfreadwrite/tests/x86_64-windows/mfreadwrite_test.exe
xvfb-run -a wine dlls/mfreadwrite/tests/x86_64-windows/mfreadwrite_test.exe mfplat
```

Check both `MF_SOURCE_READER_FIRST_AUDIO_STREAM` and
`MF_SOURCE_READER_ANY_STREAM` results; success requires both refcount assertions
actually to execute, not merely that the test launches.

For a selective test with the system Wine runtime, load the locally compiled
`mfreadwrite` from a disposable prefix; verify the actual module path with
`WINEDEBUG=+loaddll`. The focused ownership harness reuses the same assertion
and mock media source, after one warm-up read. It distinguishes exit 2 before
0063 (both samples still have refcount 2) from exit 0 after the fix (730 checks,
no failures or skips). The full `mfplat` test binary was also run with the
candidate reader in the mixed host runtime; unrelated failures and a timeout
prevent treating the full suite as green.
