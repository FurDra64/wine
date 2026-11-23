# Diagnose the duplicate window-manager provider and stale tray request

This is a **shadow-only** fix, not a production patchset. Do not add
`window-manager-provider.patch` to `patches/series.conf` or apply it to the live
checkout. The patch applies after the stack, not to pristine Wine sources.

## Fix

- Remove GE's `BOOL    (*pHasWindowManager)(const char *name);` after
  `pWindowPosChanged`. Keep Valve's `BOOL    (*pHasWindowManager)(const char *);`
  after `pFlashWindowEx`. The signatures are identical, but the slots are not
  interchangeable: the loader's positional initializer uses the Valve slot.
  The X11 and Wayland designated initializers both use that surviving member.
- Keep `systray.c`, `queue.c` and `protocol.def` unchanged. The series already
  defines `set_user_input_time.forward` in `ge-em-fixups/0063`. Run
  `tools/make_requests` after applying the full series. For both tested bases the
  generated version goes from 981 to 982; the request offsets are `set=12`,
  `forward=16`, request size 24; the reply time offset is 8 and reply size 16.
  Build the client and server from the same generated files. Do not mix binaries
  from builds with different request layouts.

## Reproduce the landing verification

Use the landed base `353417384507271d60bfdaf4d7841aedcc599f72`. In Bash, from a
clean checkout of this diagnostic branch, export that base into fresh scratch
space (set `TMPDIR` to a scratch directory first):

```bash
set -euo pipefail
export LC_ALL=C
fix="$PWD/docs/diagnostics/window-manager-provider.patch"
root=$(mktemp -d "${TMPDIR:?}/window-manager-provider.XXXXXXXX")
mkdir "$root/shadow" "$root/build"
git fetch --no-tags origin 353417384507271d60bfdaf4d7841aedcc599f72
git archive 353417384507271d60bfdaf4d7841aedcc599f72 | tar -x -C "$root/shadow"
cd "$root/shadow"
git init -q
git add -A
bash scripts/apply-patches.sh --destdir "$PWD"
test -s dlls/winewayland.drv/wayland_touch.c
cp -a "$root/shadow" "$root/build-src"
cd "$root/build-src"
git apply -p1 --check "$fix"
git apply -p1 "$fix"
./tools/make_requests
sha256sum include/wine/server_protocol.h server/request_{handlers,trace}.h > "$root/first.sha256"
./tools/make_requests
sha256sum --check "$root/first.sha256"
autoconf -o configure configure.ac
cd "$root/build"
"$root/build-src/configure" --enable-archs=x86_64 --disable-tests --with-wayland
```

The series already includes `ge-wine-wayland` on this base. The initial
`9a35204440069165e61c0a80168aed34d5b663c1` gate instead used the ordinary series
first and then the approved top-level Wayland prefix through 0255. That older
shadow needed a whitespace-only pre-image adjustment to 0161; do not carry it
forward to the landing base.

On both bases the compiler rejected the 0235 assignment in `d3dkmt.c`: the
helper returns `struct d3dkmt_object *`, not `struct d3dkmt_adapter *`. After
reproducing that error, only in the diagnostic build-source copy, use
`(struct d3dkmt_adapter *)get_d3dkmt_object( desc->hAdapter, D3DKMT_ADAPTER )`
in the `KMTQAITYPE_UMDRIVERNAME` branch. The object is the adapter's first
member and the helper checks the adapter type tag. No production patch changes.

From the build directory, run:

```bash
make -j12 dlls/winewayland.drv/{display,opengl,vulkan,wayland,wayland_data_device,wayland_keyboard,wayland_output,wayland_pointer,wayland_surface,wayland_touch,waylanddrv_main,window}.o \
    dlls/win32u/{vulkan,d3dkmt,opengl,message}.o
make -j12 dlls/win32u/all dlls/winewayland.drv/all
make -j12 dlls/win32u/systray.o server/queue.o dlls/winex11.drv/all server/wineserver
```

The landing build produced all 16 nonempty x86-64 ELF relocatables, both ELF
and PE outputs for win32u and the Wayland and X11 drivers, and the matching
wineserver. Compiler warnings are not zero: both object gates reported the
same unused function/variable diagnostics; the two main DLL build gates also
had the same normalized warning set across the two fixed builds. The unfixed
reference cannot complete a build, so this is not a full comparison against an
unfixed build.
