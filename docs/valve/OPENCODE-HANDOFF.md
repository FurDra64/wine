# OpenCode handoff — Valve Wine forward port (2026-11-03)

## Read first
The user is taking this task over directly in OpenCode. Do not wait for Codex,
call Codex, or rely on the old completion bridge. Codex Goal remains paused.
Use opencode-go/muse-spark-1.3-contributor via Headroom; never --pure.
Read /mnt/hdd/repo/wine/AGENTS.md, nested instructions, and
/home/furdra/.codex/skills/opencode-delegate/SKILL.md.
Shared repository: preserve others' edits and all pre-existing worktrees/files.
Japanese user communication. No commits/push/publishing without authorization.

## Binding objective
Port ALL ValveSoftware/wine bleeding-edge downstream functionality onto Wine
11.21 in FurDra64/wine. Preserve upstream 11.21. Deliver reusable patches under
patches/, integrate existing 5 patchsets, and maintain continuous Valve tracking.
Upstream-owned source in the primary repository must not be edited directly.
Do not replace the task with old-base raw export or tracking-only scripts.

## Verified state on handoff
NOT COMPLETE. No Valve feature patchsets have been installed in primary patches/.
The old source implementation processes are no longer present. The lead's final
message explicitly stopped at partial media work, networking stopped after its
increment, core reported UnknownError: Failed to execute statement. Graphics has
an unfinished last message but no corresponding live implementation process was
found. Old delegated-status.json state=working is STALE, not liveness evidence.
Do not assume old workers remain active. Unrelated interactive OpenCode processes
exist; never kill/reassign them. All partial source trees remain preserved.
Event bridge has no terminal receipt and no running owned watcher was found;
arming file removed during this handoff to prevent future unsolicited Codex wake.

## Pins and repository
Primary: /mnt/hdd/repo/wine
master: 454a75ddc0b04443aa352ca3a40241edc5ad6557
upstream Wine 11.21: 2528aff26208257fdbf980666a4f0e66d47563ce
Valve base Wine 11.0: db11d0fe6a169c457e23d007e20404643d067aa8
Valve bleeding-edge: fda79a585939fb7512dc220a11249f9ffe825fcf
1919 source commits; 554 patch-id equivalent upstream, 1365 unique by patch-id.
This does NOT prove semantic feature coverage. Initial actual merge had235 conflicts.
Raw Valve reconstructed tree: 57167af0ac6f80ce7865ed7c52c6493091358a29.
Pre-existing .omo/, .serena/, IDEA.md are user-owned; preserve them.

## Recover existing source work; do not start from zero
Run root: /tmp/wine-valve-ulw.U8xysA — DO NOT DELETE.
Core worktree: /tmp/wine-valve-ulw.U8xysA/core-port
Graphics worktree: /tmp/wine-valve-ulw.U8xysA/graphics-port
Networking worktree: /tmp/wine-valve-ulw.U8xysA/forward-port
Media worktree (exact nested path):
/tmp/wine-valve-ulw.U8xysA/media-port/media-port-v2
They contain unfinished Git merges, staged resolutions, and clean automatic
merge changes. Do not reset/abort/checkout wholesale or lose clean merge deltas.
Revalidate each tree's current Git index/unmerged paths before changing it.
Separate workers must own disjoint trees/paths; never concurrent same-tree writers.
Never pipe mutating commands to head/tail (a previous merge was interrupted).

Prior sessions (history references, not active jobs):
- lead/media ses_e67a61c73ffe43eOWR281QO4Cb
- core ses_e68066eb0ffe3SRtdLoIfLzyDT
- graphics ses_e67ed5a4fffe9IeGdawjI7DMxy
- networking ses_e67f4f8deffeUQ1PylpCxD5H5v
Old lead ses_e67ed56f0ffeOR9LTE3UE1cFMQ failed, do not use as live owner.
Session history can be resumed explicitly; fresh session is preferable if old
context/database errors recur. Never --continue (may select unrelated session).

Networking worker reports 9/9 group conflicts resolved, artifacts/networking.patch
in forward-artifacts, but no combined build/feature verification yet.
Media lead stopped after original six MF paths plus3 B1 files staged, about33
media conflicts remained at that report; recompute current counts.
Six-file validation covers clock/session x64+i386, MF test sources x64, IDL widl;
it is NOT full Wine validation. A real missing brace in clock.c was fixed by Codex
and compiled both arches; preserve that fix. Media progress/validation files may
be inside the effective media tree; locate them rather than assuming root paths.
Core and graphics decisions/progress are in copied artifact directories and
original run root; not equivalent to accepted final implementation.

## Cross-module gaps explicitly requiring proof/fixes
G1 ARM64EC exit thunk from Valve b24ecb4824a, upstream moved to libs/winecrt0/arm64ec.c.
G2 Registry load/unload64KEY counterpart semantics (helpers were removed unresolved).
G3 ICU/webservices prefer-native behavior was dropped; restore parity.
G4 Vulkan1.spec: regenerate from combined graphics sources/schema.
G5 configure/config.h.in: regenerate.
G6 ntdll/ntsyscalls outputs: regenerate.
G7 hardware message VARARG(extra), SEND_HWMSG flags, track_mouse across server/client.
G8 bool/rawinput queue signatures.
G9 d3dkmt wait/signal client/server agreement.
G10 IYUV color conversion across colorcnv/winegstreamer.
Media immediate next step: upstream dsound FIR mixer rewrite vs Valve get_mono/
put_* conversion coverage, including dsound_convert.c deletion conflict; establish
semantic equivalent coverage rather than dropping Valve changes.
Read copied opencode-lead-task.txt for complete prior delegation and ownership.

## Already implemented primary tracking tools (uncommitted)
scripts/valve-track.sh; scripts/valve-track-selftest.sh;
.github/workflows/valve-track.yml; docs/VALVE-TRACKING.md;
docs/valve/pins.conf; inventory-bleeding.tsv; conflicts-11.21-vs-bleeding.txt.
Parent previously independently verified:
- 38 CLI/Git fixture behaviors, ShellCheck0.11, actionlint1.7.7 PASS.
- actual extracted workflow harness9/9 PASS.
- actual1919-patch reconstruction exactly matches pinned source tree PASS.
- existing5sets/9patches dry-run and actual isolated application PASS.
These validate tracking/export and existing overlay only. They DO NOT prove the
forward port, combined build, runtime behavior, or whole feature completeness.
Tests need repeat only if relevant inputs change.
Logs and raw-export-A/B/C remain under run root; don't redo1919 just to get green.

## Build resources and validation still required
baseline-build configured --enable-archs=i386,x86_64 against pristine main source;
baseline-build.log records its build, final result must be checked, not assumed.
Do not run two make processes in one build directory. Actual combined tree needs
configure, regenerate, both PE architectures build, appropriate Wine tests and
runtime smoke, compared against baseline. Host has MinGW32/64, autoconf, clang,
Xvfb, GStreamer/Pulse/Vulkan/FFmpeg/X11/Wayland; use8jobs, task-owned cache only.
Baseline missing optional OpenCL dev/libsane/gphoto2/OSSv4/capi20; no extra disabling
to pass. User declined Biome installation: do not install it.

## Completion criteria
1. Resolve all source groups with semantic feature accounting of all1919 commits,
   including upstream equivalents, regenerated changes, cross-module gaps above.
2. Assemble one combined integration tree after owners stop, preserve upstream11.21.
3. Build/test combined tree and existing overlays with literal evidence/results.
4. Deliver reviewed feature/dependency patchsets in primary patches/ and series.conf.
5. Actual full application into fresh pristine11.21 must equal reviewed combined
   tree; --check alone does not suffice. Tracking docs/CI reflect actual final port.
6. Report feature/build/test limitations honestly; no complete label from marker
   removal alone. Preserve evidence, then clean only task-owned resources.
No requirement to return to Codex. The user will run this directly in OpenCode.

## Evidence preservation
Durable metadata/artifacts copy: /mnt/hdd/repo/wine-valve-handoff-20261103
Full original notes: ulw-20261102.e1mdPl.md in that directory.
This copy contains metadata and available small artifacts, NOT a backup of live
source worktrees or all build logs. Keep /tmp/wine-valve-ulw.U8xysA intact until
resolutions are safely exported/moved via Git worktree commands and verified.
