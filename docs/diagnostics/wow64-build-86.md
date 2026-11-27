# WOW64 build #86: overlay compile repairs

Base: `456af7e7c8d0e730a252bb4d99d6a860981e991a` on
`fix/build-regenerate`. The [GitHub Actions run][ci] passed configure but
failed compiling i386 `dlls/ntoskrnl.exe/pnp.c`.

- `valve-revert/0001` removes the asynchronous BusRelations queue and
  invokes `handle_bus_relations()` inline. Mark that build mode locally in
  `pnp.c`. Guard the queue cleanup in `ge-bluetooth-le-0008` so builds
  with a queue still drop pending updates on `IRP_MN_REMOVE_DEVICE`.
- `valve-common-interfaces/0001` redeclared
  `PDH_FMT_COUNTERVALUE_ITEM_{A,W}` and their pointer typedefs. The base
  already has the same named types, member types and member order, as
  well as their A/W aliases. Drop only the redundant header hunk.
- `valve-d3dx10/0001` carries a truncated fragment of
  `D3DX10CompileFromMemory`. The actual implementation is already built
  from `dlls/d3dx9_36/d3dx10_compiler.c`; retain the async processor and
  remove only the stray fragment.
- `valve-d3dx10/0004` calls the missing
  `ID3DBlob_GetBufferPointer` macro. Use the C macro for `ID3D10Blob`,
  the same interface underlying the `ID3DBlob` typedef.
- `valve-d3dx10/0003` referenced a texture descriptor helper and an
  RGBA test fixture that were missing from the port. Restore both from
  [the Valve source][valve]; keep the SaveTexture tests and their assertions.

- `ge-wine-wayland/0235` uses the typed D3DKMT adapter accessor
  rather than assigning the generic object pointer to an adapter.
- Archive `ge-wine-wayland/0107` unchanged: [Wine upstream][wic] already
  provides the intended RGBA/BGRA to 64-bit RGBA behavior, and the base
  also has conversion tests for both. The erroneous replay had landed
  in the 128-bit float converter instead. The effective converter file
  is byte-identical to the base after removing that replay.
- `ge-wineland-child-rendering/0088–0092` update the surface and driver
  initializer layouts, carry fractional DPI over the hit-test request,
  preserve both WGL interop names, and restore Wayland declarations
  and call arguments. The DMA-BUF syscalls are appended to the generated
  tables with explicit IDs so no existing syscall is renumbered.
  Build Wine's client and server together.

- `ge-video-rework/0105` imports the DMO category GUIDs from the existing
  `dmoguids` archive instead of defining duplicate copies in the QASF
  test object. The test cases and GUID values are unchanged.

- Install the FFmpeg development libraries in the existing CI job;
  the active `winedmo` overlay links swresample and swscale. No build
  modules, triggers or tests are disabled. `ge-video-rework/0106`
  uses the forward-declared `struct SwsContext` for older FFmpeg headers.

From a clean checkout with the same build dependencies as CI:

```sh
bash scripts/lint-series.sh
bash scripts/apply-patches.sh --check
bash scripts/apply-patches.sh --all
./tools/make_requests
./configure --enable-archs=i386,x86_64
make -j"$(nproc)"
```

[ci]: https://github.com/FurDra64/wine/actions/runs/45744864064
[valve]: https://github.com/ValveSoftware/wine/blob/c7b2ce3ab42/dlls/d3dx10_43/tests/d3dx10.c
[wic]: https://github.com/wine-mirror/wine/commit/f83483b37fbfc8ea76fa4811bef87aea97175fae
