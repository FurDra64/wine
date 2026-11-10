# NEXT-SESSION-PROMPT — Valve forward-port Wine 11.21 継続指示 (CHECKPOINT完了・全移植納品未完了)

> 状態: CHECKPOINT完了・全移植納品未完了。全移植完了と呼ばないこと。
> ユーザーは現行export/replay TODO完了後に区切ることを選択した。作成元の旧セッションは停止済み。
> 次セッションでユーザーが本ファイルを参照して再開を依頼したら、以下の未完了作業を進める。旧セッションへの停止指示は、次セッションの再開を妨げない。

## 0. そのまま貼る次セッション開始文 (TOP・コピペ用)

```text
このファイル (/mnt/hdd/repo/wine/docs/valve/NEXT-SESSION-PROMPT.md) と
/mnt/hdd/repo/wine-valve-handoff-20261103/validation-native/export-checkpoint/CHECKPOINT.md (63行) を読み、
未完了のValve feature forward-port (Wine 11.21目標) をネイティブMuse taskで再開せよ。
primaryのupstream所有領域 (dlls/・server/・include/等) は直接編集しない。
patches/・scripts/・.github/・docs/ は納品先として変更可。
委譲はOh My OpenAgentの通常のtaskを使い、Muse Sparkを優先する。
headroom wrap opencode / opencode run の二重起動、無断commit/pushは禁止。
まず §1 pins/§2 TREE/§5 未完了ゲート/§6 リソース規則を確認し、ABSパスと実コマンドで1件ずつ進めよ。
```

## 1. 継続条件・経路・所有権

- 親は通常の `task` でネイティブのサブエージェントへ委譲し、子は原則として再委譲せず直接作業する。CLIによる別OpenCode起動・無断commit/push・global config変更・機能無効化による見せかけの合格は禁止。
- 実装は原則 `category='unspecified-high'` または `'quick'` を使う。現在の設定ではMuse Spark 1.3。writing/explore/librarian等も適切な用途で設定を確認しMuseを優先する (`/home/furdra/.config/opencode/oh-my-openagent.json`)。
- deep/ultrabrain/oracle/prometheusは高コストのため乱用禁止。Oracle相談済み `ses_e5e909629ffeePc0xAMtCXalu1` 1件のみ。稼働中Oracleなし。
- 旧広域 `#2 ses_e61e64d05ffeOqoeeo0e83HQK9` (600Kループ) は再開禁止。HISTORY参照のみ。
- 分割は1 API契約・少数ファイル単位。リテラルABSパス・実コマンド・tool/time予算・6callマイルストーン・2ラウンド無進展で復帰を付けよ。agentの「done」ではなく実exit・実artifactで検証せよ。
- Wine/source/testパスは全てABS。pristine PRIMARY誤読・相対artifact誤書きが多発したため。
- writerは分離worktree/shadowで、canonical writer/makeは1つのみ (最大-j8)。canonical並列make禁止。
- ユーザー所有の `.omo/`・`.serena/`・`IDEA.md` と既存treeを保持。旧4未完merge (`core-port,graphics-port,forward-port,media-port/media-port-v2`, ROOT下) はREADONLY歴史扱い。reset/abort/drop/clean禁止。
- CLI worker/Codex bridge不要。共有Headroom 8787は無関係・不干渉。
- 旧TODOの残りは今回の区切りで次セッションへ延期した。中止/延期ステータスは未完了を意味し、完了ではない。

## 2. 確定CHECKPOINT (引継ぎ時点の検証済み参照状態)

- ROOT: `/tmp/wine-valve-ulw.U8xysA`
- SOURCE: `/tmp/wine-valve-ulw.U8xysA/integration-native`
- BUILD: `/tmp/wine-valve-ulw.U8xysA/combined-build-native` (canonical `make -j8` EXIT 0)
- BASELINE: `/tmp/wine-valve-ulw.U8xysA/baseline-build`
- PRIMARY: `/mnt/hdd/repo/wine` (pristine upstream SOURCE・直接編集禁止)
- HDDROOT: `/mnt/hdd/repo/wine-valve-handoff-20261103/validation-native`
- CHECKPOINT: `HDDROOT/export-checkpoint/CHECKPOINT.md` (63行全文が正)。旧 `ROOT/export-native/candidate-patches` と旧スナップショ `810bb/05d846` はSTALE歴史扱い。削除・最新扱い禁止。
- ポインタ: `/tmp/wine-valve-ulw.U8xysA/export-native/CURRENT-CHECKPOINT.md` (11行) がHDD CHECKPOINTを指す。
- FINAL現source TREE: `9e7284280a8d308659a9dc1403980ff566d06666` (既存5 overlay含む)
- Valve-only TREE: `8329ab787e2197feadf0b4f1536a69eb69f03a45`
- 13候補feature/依存set・581 paths・unassigned 0・dup 0。fresh 13適用treeがValveと完全一致→既存5sets/9patches適用でFinalと完全一致。cumulative `--check` 18 EXIT 0。
- raw log/manifest/candidate-series/candidate-patchesは全て `HDDROOT/export-checkpoint` 下。
- バイナリICO 1件のため `--backend git-apply` が必須。最新primary scriptは `--whitespace=nowarn` をbackend実適用とcheck両方に修正＋diff `--git` からbinary seed。12/12 test＋ShellCheck 0.11.0ともに0。旧8byte空白mismatch解決済み。
- 現HEAD upstream pin不変・private index TREEはWORKING＋新規tracked取得 (stale indexでない)。
- 次セッションでsourceを修正したら新しいsnapshotとreplay証拠を作る。このcheckpoint自体は過去の証拠として保持する。

## 3. pin (full SHAはCHECKPOINT通り・短縮展開しない)

- target: `2528aff26208257fdbf980666a4f0e66d47563ce`
- source: `fda79a585939fb7512dc220a11249f9ffe825fcf`
- common base: Wine 11.0 `db11d0fe6a169c457e23d007e20404643d067aa8`
- primary master: `454a75ddc0b04443aa352ca3a40241edc5ad6557` (unchanged)
- CHECKPOINT 14行目「base tree」はupstream 11.21のfixture tree `db03e4c9d9d2c973fbe7e73ee88a13b459a92ae5`。common base Wine 11.0のtreeは `c143c87e72ecf5e6795b7bd802983bec54c345f4`。親が両commitの `^{tree}` で確認済み。commit SHAと変更済みTREEを混同しない。外部fetch・1919raw再構成不要 (Git objects揃い)。

## 4. primary現状 (親確認済み・今回変更なし)

- `M scripts/apply-patches.sh`、untracked `scripts/apply-patches-selftest.sh`
- 旧tracking未commit: `.github/workflows/valve-track.yml`、`docs/VALVE-TRACKING.md`、`docs/valve/`、`scripts/valve-track.sh`、`scripts/valve-track-selftest.sh`。
- ユーザー所有の `.omo/`・`.serena/`・`IDEA.md` は保持。旧 `docs/valve/OPENCODE-HANDOFF.md` は旧CLI経路・旧数値で陳腐化。歴史参照のみで上書き禁止。本ファイル＋CURRENT-CHECKPOINTを優先する。
- 誤root由来のtask artifact (`integration-native-artifacts/`、`jscript-native-artifacts/`、`media-artifacts/`、`recovery-contract-audit.md`、`runroot/`) は証拠保持。盲目削除・commit禁止。所有権つきcleanupは後。
- `patches/series.conf` は依然ORIGINAL 5のまま。13は未install。
- 追跡tool `scripts/valve-track.sh`＋38 fixture cases・workflow 9 harnessは未commit初期作業。tracking/raw 1919再構成をport完成と等価扱い禁止。
- `ROOT/coverage-native/{commitcoverage.tsv,feature-evidence.tsv,feature-commit-joint.tsv}` の1919行・554 patch-id equiv・1365 uniqueはqualified proofのみ。1406 superseded candidate・semantic mappingは全証明でない。owner/patch-idで全implemented扱い禁止。

## 5. 未完了ゲート (次セッションの再開対象)

A. GLX/DIB: baseline opengl exe (SHA `195741f5...`) はEGL 11988/0fail/39skipでSAME。CURRENT既定Valve GLX DIB `wglMakeCurrent` false。native GLX ctx (onscreen fmt1＋pbuffer bitmap fmt241) はMakeContextCurrent TRUEだがglGetString NULL。matching FBConfig native controlは4.6動作。Valve `WINE_USE_EGL` gateは意図 (unique Valve) のため保持。EGL強制・gate除去・NULL guard修正主張禁止。証拠 `HDDROOT/gl-dib-debug/artifacts/{report.md,report-next.md,backend-parity.md}`。現 `dlls/win32u/opengl.c` のget/make_thread_context_currentはprofile/no-errorをcacheするがformatを見ない。READY shadow候補 `HDDROOT/glx-format-fix/candidate/opengl.c` (seed `d240badd...`・candidate `1621d3d0...`)、`corr.patch` 87行、`NOTE.md`。format-aware cache・新slot bind後に旧slot破棄 (TEB glReserved2 dangle回避)・同Root/profile/no-error・public ABI不変。TU compile＋helper policy＋native GLX test PASSのみ。未import・未WineDIB検証。次はlifetime/sharegroup精査→最小DIB→SAME full GL。compileで根本原因主張禁止。候補actor `ses_e5c9e185effe45y1GV9oY68gBw` は任意参照、診断 `ses_e5e6141c0ffeWoQoJppYsAhea9` は長大のため無制限再開禁止。
B. MF MP4 metadata 2件hard (1465 fails内): SAME PE probe (SHA `b1ec1791...`) 4run実測。証拠 `HDDROOT/mf-source-probe/artifacts/result.md`＋log。BASE mediaSource vtbl `winegstreamer.dll` はdecoded AAC float/MP3 PCM＋ALL_SAMPLES_INDEPENDENT 1。CURRENT `mfmp4srcsnk.dll` はcompressed AAC `00001610`/MP3 `00000055`・ALL欠落 hr `C00D36E6`。handler/type vtbl generic `mfplat.dll` はproducerでない。次は `mfmp4srcsnk` stream type構成の実修正。winegstreamer/source fallback優先・format rank・todo変更は不可。compressed passthrough・新Valve機能保持。Windows/MediaType意味でALLのみ検証しVBRにFIXED TRUEを付けない。旧winegstreamer 2 hunksはseed (`mfplat 19bd69...`/`media_source f817fd...`) へ完全revert済み。再適用禁止。probe actor `ses_e5c9e10a2ffeaR49hXbTDZm8wH` (fresh小)、旧23分metadata actorは回避。baseline MFplat TEST exe実path `baseline-build/dlls/mfplat/tests/x86_64-windows/mfplat_test.exe` (SHA `32d059d4...`)。CUR `6e6c1ed9...` はbaselineでない。SHA省略形で創作禁止。現MFplat crash 139→解消、15574x3 bounds FIXED、7306 XVP FIXED (実D3D11 HW/noSkip/S_OK/deadbeef)。残2件はmetadataのみ。XVP sourceはcanonical unsupported D3D11 processor→CPU fallback (GPU valid・errors OOM/INVALIDARG保持)・full make 0。現 `mf_transform` WMA abortはProton audio-converter bin nonempty (`MEDIACONV_AUDIO_DUMP_FILE` rank 65保持・plain fallback avdec WMA) でclose。AAC/type enum残差はpaired logでTODO/HARD分類。exit count単独で断定禁止。
C. Core paired: same-corpus reg/exception x64＋reg i386は0 new fails。i386 exception 12 failsは両方same (assert multiset)。dsound 7108/0、msctf 289/0、winhttp notification 0。Healthy HTTP 721完了・hard regressionなし。7 TODO successesは実87 invalid URL/183 duplicate vs旧120で説明済み (http-listener-prefix・Windows正規)。HTTP 1053/HANGはTMPFULL fixtureでありHTTP本番修正禁止。全Wine suite・GPU/VR/ARM64EC runtime証明なし。ARM64EC exit thunk asmのみ。optional vosk/piper dev lib/model欠如は現状記録のみ。green目的のinstall/disable禁止。tested/unverifiedを正直記録。

## 6. リソース規則 (厳守)

- `/tmp` 61G満杯 (2GB prefix多数) で誤QA hang/半端reg発生。16 OWN prefixをHDD移行済み。tmp 26G free。
- 証拠 `HDDROOT/resource-migration.md`、`prefix-map.tsv`、`future-env.sh`。
- 新規prefix/TMPDIR/XDG_CACHE_HOME/GST_REGISTRYは全てHDD task-owned。HOME不変。全Wine/wineboot/wineserver/gdbに明示 `WINEPREFIX/WINESERVER`。
- 旧破損prefix再利用禁止。disk headroom＋`system.reg`/bootstrap readyを検証。own server/Xvfb PIDは領収書つきteardown。generic pkill禁止。
- 非owned DISPLAY `:0`・`~/.wine` process (例 2902886等) はkill/touch禁止。PID再利用のためenviron/exe/ancestryで現況確認。
- 元ROOT `/tmp/wine-valve-ulw.U8xysA` は削除・移動禁止。旧source worktree/build/raw export保持。将来worktree GCはdurable export証明後のtask-ownedのみ。

## 7. runtime後に残るもの

- source変更後は最新13再export＋byte exact 13＋5 fresh replay再実施。
- 独立高厳格review未了。delivery/docs/CI更新未了。review済み検証setのみactivate。既存5保持。
- pipeline CI/docsは13 binary有効のためリテラル `--backend git-apply` (default backend patch不変)。

## 8. 次の最小5手 (次セッションで実施)

1. 候補GLX (`HDDROOT/glx-format-fix`) 精査→最小DIB→SAME full GL。
2. MF MP4はprobe＋`mfmp4srcsnk` stream type実修正 (fallback優先変更なし)。
3. 同一test exeによるpaired runtimeで既知baseline失敗・TODO成功・新規hard failを区別する。未実施のGPU/VR等は検証限界として明記し、合格扱いにしない。
4. 変更あれば13再export＋13＋5 replay＋cumulative check。
5. review＋primary delivery/docs/CI/cleanup (review済みのみ)。
