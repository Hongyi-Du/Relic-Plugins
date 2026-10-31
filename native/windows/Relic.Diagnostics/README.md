# Native UI thread snapshot (CI diagnostics only)

`Relic.NativeStack.exe --pid <owned Relic PID>` is a small x64 C++ helper built
only by the explicit Windows diagnostic workflow. It refuses to run unless
both `GITHUB_ACTIONS=true` and `RELIC_PERF_DIAGNOSTIC=true`. It is not packaged
with the product and must not be built or run on the person's desktop.

It locates the largest visible top-level window belonging to the given PID
using `EnumWindows` / `GetWindowThreadProcessId`, opens that UI thread, and
checks its process ID again. The short suspension scope copies the SDK's real
`CONTEXT` and up to 256 KiB from the stack pointer through its contiguous
committed memory region. A scope guard balances `SuspendThread` with
`ResumeThread`, including exception exits. The thread resumes **before** any
DbgHelp initialization, stack walking or symbol lookup. No raw stack bytes are
written to artifacts.

`StackWalk64` uses the captured stack through its memory callback, and the
standard `SymFunctionTableAccess64` / `SymGetModuleBase64` callbacks. A matching
`CBA_READ_MEMORY` callback also routes symbol-handler stack reads to the copy.
This avoids a hand-written ABI, CONTEXT, PE or unwind-table parser. DbgHelp runs
on one thread. Symbol search is restricted to the helper's local
`symbols-local` directory; environment, CodeView and image-directory paths are
ignored, symbol-server autodetection is disabled, and no SRV/download path is
configured. Available local module/export names and displacements supplement
the raw addresses; missing names are left empty.

Stdout is JSON Lines: `native_snapshot` records the PID, UI thread, window,
actual suspend duration, copied bytes, truncation and confirmed resumption;
`native_frame` records instruction/stack pointers and optional local lookup;
`native_summary` records completeness, stop reason and duration. The walker
validates the initial PC and every prospective frame with `VirtualQueryEx`:
the PC must be in `MEM_COMMIT` memory with a `PAGE_EXECUTE*` protection and
without `PAGE_GUARD` or `PAGE_NOACCESS`. Each SP must be eight-byte aligned,
inside the actual captured stack bytes, and advance beyond the previous SP.
The first StackWalk64 result may repeat the already-validated initial frame;
it is skipped, not counted twice. Any invalid candidate stops unwinding with
`complete:false` and an explicit reason. Its IP/SP appear only in a separate
`native_unwind_rejected` record, never as `native_frame`. This prevents heap
values and small integers encountered after missing JIT unwind data from
becoming spurious native frames. Executable-address validation is a necessary
sanity check, not a substitute for managed unwind metadata or proof that an
entire cross-JIT stack is complete.

The walker has 96-frame and two-second soft limits. All accepted raw addresses are
emitted even if symbol lookup runs out of time. Incomplete contiguous stacks,
unavailable unwind data, JIT frames and repeated frames are not presented as a
complete call stack. The outer diagnostic driver imposes the five-second hard
process deadline after the thread has normally already resumed.

This operation temporarily suspends the sampled thread and therefore affects
responsiveness. It is only a diagnostic signal, never acceptance evidence.
The shared driver samples only its own synthetic CI application and retains
separate `native-stack-*` and `managed-stack-*` files.

For post-processing, each frame additionally retains the actual loaded image
path, base, size, timestamp, checksum and symbol/export type. A separate mode,
`--resolve <image> <local-symbol-dir> <offsets...>`, requires `GITHUB_ACTIONS=true`
but never opens or suspends the target process. It loads the supplied image and
local PDB with `SYMOPT_EXACT_SYMBOLS`; unresolved or unmatched symbols remain
explicit failures, with no export fallback. `scripts/performance/resolve_symbols.py`
downloads the exact RSDS GUID/age PDB from Microsoft's public server after the
measurement has ended, then invokes this local-only mode. The raw snapshots
and the original responsiveness result are unchanged. Downloaded PDB caches
are excluded from artifacts; their exact identity, source and resolved frames
are retained in `resolved-symbols.json`.

SDK contracts used:

- [GetThreadContext](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getthreadcontext)
- [StackWalk64 and its callbacks](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-stackwalk64)
- [SymInitializeW local search path](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-syminitializew)
- [SymSetOptions](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nf-dbghelp-symsetoptions)
- [CBA_READ_MEMORY callback](https://learn.microsoft.com/en-us/windows/win32/api/dbghelp/nc-dbghelp-psymbol_registered_callback64)
- [VirtualQueryEx page state and protection](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualqueryex)
