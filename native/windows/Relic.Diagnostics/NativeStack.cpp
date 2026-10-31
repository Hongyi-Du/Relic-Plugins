// CI-only x64 UI stack snapshot. No target code is injected or executed.
#include <Windows.h>
#include <DbgHelp.h>
#include <algorithm>
#include <array>
#include <cstring>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#if !defined(_M_X64)
#error Relic.NativeStack requires an x64 build and x64 target.
#endif

namespace {
constexpr SIZE_T StackCapacity = 256 * 1024;
constexpr size_t FrameLimit = 96;
constexpr ULONGLONG WalkBudgetMs = 2000;

[[noreturn]] void Fail(const char* operation) {
    throw std::runtime_error(std::string(operation) + ": Win32 error " + std::to_string(GetLastError()));
}

struct Handle {
    HANDLE value;
    explicit Handle(HANDLE handle) : value(handle) {
        if (!value || value == INVALID_HANDLE_VALUE) Fail("Open handle");
    }
    ~Handle() { CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};

struct SuspendedThread {
    HANDLE thread;
    bool active = true;
    DWORD previous;
    explicit SuspendedThread(HANDLE handle) : thread(handle), previous(SuspendThread(handle)) {
        if (previous == static_cast<DWORD>(-1)) Fail("SuspendThread");
    }
    void Resume() {
        if (active && ResumeThread(thread) == static_cast<DWORD>(-1)) Fail("ResumeThread");
        active = false;
    }
    ~SuspendedThread() {
        // Exception paths also release exactly the suspend count we acquired.
        if (active) ResumeThread(thread);
    }
};

std::string Hex(DWORD64 value) {
    std::ostringstream text; text << "0x" << std::hex << value; return text.str();
}

std::string Quote(const std::string& value) {
    std::ostringstream text; text << '"';
    for (const unsigned char ch : value) {
        if (ch == '"' || ch == '\\') text << '\\' << ch;
        else if (ch < 0x20) text << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(ch);
        else text << ch;
    }
    text << '"'; return text.str();
}

bool EnvTrue(const wchar_t* name) {
    std::array<wchar_t, 16> value{};
    return GetEnvironmentVariableW(name, value.data(), static_cast<DWORD>(value.size())) == 4
        && std::wstring(value.data()) == L"true";
}

struct WindowTarget { DWORD pid; HWND window = nullptr; DWORD thread = 0; LONGLONG area = -1; };
BOOL CALLBACK FindWindow(HWND window, LPARAM data) {
    auto& target = *reinterpret_cast<WindowTarget*>(data);
    DWORD pid = 0;
    const DWORD thread = GetWindowThreadProcessId(window, &pid);
    if (pid != target.pid || !IsWindowVisible(window)) return TRUE;
    RECT rect{};
    if (!GetWindowRect(window, &rect)) return TRUE;
    const auto area = static_cast<LONGLONG>(rect.right - rect.left) * (rect.bottom - rect.top);
    if (area > target.area) { target.window = window; target.thread = thread; target.area = area; }
    return TRUE;
}

struct Snapshot {
    CONTEXT context{};
    std::vector<unsigned char> bytes = std::vector<unsigned char>(StackCapacity);
    DWORD64 stackStart = 0, regionStart = 0, regionEnd = 0;
    SIZE_T copied = 0;
    bool truncated = false;
};
Snapshot* currentSnapshot = nullptr;

BOOL CALLBACK ReadSnapshot(HANDLE process, DWORD64 address, PVOID buffer, DWORD size, LPDWORD read) {
    if (read) *read = 0;
    const auto& snapshot = *currentSnapshot;
    if (address >= snapshot.regionStart && address < snapshot.regionEnd) {
        // Never mix the captured stack with a later, running-thread stack.
        if (address < snapshot.stackStart || address - snapshot.stackStart > snapshot.copied
            || size > snapshot.copied - static_cast<SIZE_T>(address - snapshot.stackStart)) return FALSE;
        std::memcpy(buffer, snapshot.bytes.data() + (address - snapshot.stackStart), size);
        if (read) *read = size;
        return TRUE;
    }
    SIZE_T copied = 0;
    const BOOL success = ReadProcessMemory(process, reinterpret_cast<LPCVOID>(address), buffer, size, &copied);
    if (read) *read = static_cast<DWORD>(copied);
    return success;
}

BOOL CALLBACK SymbolCallback(HANDLE process, ULONG action, ULONG64 data, ULONG64) {
    if (action != CBA_READ_MEMORY) return FALSE;
    const auto request = reinterpret_cast<PIMAGEHLP_CBA_READ_MEMORY>(data);
    return ReadSnapshot(process, request->addr, request->buf, request->bytes, request->bytesread);
}

struct Symbols {
    HANDLE process;
    std::wstring localPath;
    explicit Symbols(HANDLE handle) : process(handle) {
        std::array<wchar_t, 32768> executable{};
        const auto count = GetModuleFileNameW(nullptr, executable.data(), static_cast<DWORD>(executable.size()));
        if (!count || count >= executable.size()) Fail("GetModuleFileNameW");
        const auto folder = std::filesystem::path(executable.data()).parent_path() / L"symbols-local";
        localPath = folder.wstring();
        if (localPath.size() < 3 || localPath[1] != L':' || localPath.find_first_of(L"*;") != std::wstring::npos)
            throw std::runtime_error("Symbol path must be one local drive directory");
        if (!CreateDirectoryW(localPath.c_str(), nullptr) && GetLastError() != ERROR_ALREADY_EXISTS) Fail("Create local symbol directory");
        SetEnvironmentVariableW(L"_NT_SYMBOL_PATH", nullptr);
        SetEnvironmentVariableW(L"_NT_ALTERNATE_SYMBOL_PATH", nullptr);
        SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME | SYMOPT_FAIL_CRITICAL_ERRORS
            | SYMOPT_NO_PROMPTS | SYMOPT_IGNORE_NT_SYMPATH | SYMOPT_IGNORE_CVREC
            | SYMOPT_IGNORE_IMAGEDIR | SYMOPT_NO_IMAGE_SEARCH | SYMOPT_DISABLE_SYMSRV_AUTODETECT);
        // Explicit local-only search; no SRV path, symbol server, or download.
        if (!SymInitializeW(process, localPath.c_str(), TRUE)) Fail("SymInitializeW");
        if (!SymRegisterCallback64(process, SymbolCallback, 0)) {
            const DWORD error = GetLastError(); SymCleanup(process); SetLastError(error); Fail("SymRegisterCallback64");
        }
    }
    ~Symbols() { SymCleanup(process); }
};

std::string FrameProblem(HANDLE process, const Snapshot& snapshot, DWORD64 ip, DWORD64 sp, DWORD64 previousSp = 0) {
    if (sp % sizeof(DWORD64)) return "unaligned stack pointer";
    if (sp < snapshot.stackStart || sp - snapshot.stackStart >= snapshot.copied)
        return "stack pointer outside captured stack";
    if (previousSp && sp <= previousSp) return "stack pointer did not advance";
    MEMORY_BASIC_INFORMATION memory{};
    if (!VirtualQueryEx(process, reinterpret_cast<LPCVOID>(ip), &memory, sizeof(memory)))
        return "instruction pointer query failed: Win32 error " + std::to_string(GetLastError());
    if (memory.State != MEM_COMMIT) return "instruction pointer is not committed memory";
    if (memory.Protect & (PAGE_GUARD | PAGE_NOACCESS)) return "instruction pointer is guarded or inaccessible";
    constexpr DWORD executable = PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY;
    if (!(memory.Protect & executable)) return "instruction pointer is not executable memory";
    return {};
}

void EmitRejected(DWORD64 ip, DWORD64 sp, const std::string& reason) {
    // A rejected candidate is evidence of the unwind boundary, never a frame.
    std::cout << "{\"kind\":\"native_unwind_rejected\",\"ip\":" << Quote(Hex(ip))
        << ",\"sp\":" << Quote(Hex(sp)) << ",\"reason\":" << Quote(reason) << "}\n" << std::flush;
}

void EmitFrame(HANDLE process, size_t index, DWORD64 ip, DWORD64 sp, bool resolve) {
    IMAGEHLP_MODULE64 module{}; module.SizeOfStruct = sizeof(module);
    const bool hasModule = resolve && SymGetModuleInfo64(process, ip, &module) != FALSE;
    alignas(SYMBOL_INFO) std::array<unsigned char, sizeof(SYMBOL_INFO) + MAX_SYM_NAME> storage{};
    auto symbol = reinterpret_cast<PSYMBOL_INFO>(storage.data());
    symbol->SizeOfStruct = sizeof(SYMBOL_INFO); symbol->MaxNameLen = MAX_SYM_NAME;
    DWORD64 displacement = 0;
    const bool hasSymbol = resolve && SymFromAddr(process, ip, &displacement, symbol) != FALSE;
    std::cout << "{\"kind\":\"native_frame\",\"index\":" << index
        << ",\"ip\":" << Quote(Hex(ip)) << ",\"sp\":" << Quote(Hex(sp))
        << ",\"module\":" << Quote(hasModule ? module.ModuleName : "")
        << ",\"module_offset\":" << Quote(hasModule ? Hex(ip - module.BaseOfImage) : "")
        << ",\"symbol\":" << Quote(hasSymbol ? std::string(symbol->Name, symbol->NameLen) : "")
        << ",\"symbol_displacement\":" << Quote(hasSymbol ? Hex(displacement) : "")
        << ",\"lookup_skipped\":" << (resolve ? "false" : "true")
        << ",\"validation\":\"executable PC and captured stack pointer\""
        << ",\"symbol_source\":\"local symbols or exports only\"}\n" << std::flush;
}

int Capture(DWORD pid) {
    const auto started = GetTickCount64();
    Handle process(OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, FALSE, pid));
    USHORT targetMachine = 0, nativeMachine = 0;
    if (!IsWow64Process2(process.value, &targetMachine, &nativeMachine)) Fail("IsWow64Process2");
    if (targetMachine != IMAGE_FILE_MACHINE_UNKNOWN || nativeMachine != IMAGE_FILE_MACHINE_AMD64)
        throw std::runtime_error("Target is not native x64");
    WindowTarget target{pid};
    if (!EnumWindows(FindWindow, reinterpret_cast<LPARAM>(&target))) Fail("EnumWindows");
    if (!target.window || !target.thread) throw std::runtime_error("No visible top-level window for target PID");
    Handle thread(OpenThread(THREAD_GET_CONTEXT | THREAD_SUSPEND_RESUME | THREAD_QUERY_INFORMATION, FALSE, target.thread));
    if (GetProcessIdOfThread(thread.value) != pid) throw std::runtime_error("Window thread PID changed");
    Snapshot snapshot;
    snapshot.context.ContextFlags = CONTEXT_FULL;
    const auto captureStarted = GetTickCount64();
    DWORD priorSuspendCount = 0;
    {
        SuspendedThread suspended(thread.value);
        priorSuspendCount = suspended.previous;
        if (!GetThreadContext(thread.value, &snapshot.context)) Fail("GetThreadContext");
        snapshot.stackStart = snapshot.context.Rsp;
        MEMORY_BASIC_INFORMATION region{};
        if (!VirtualQueryEx(process.value, reinterpret_cast<LPCVOID>(snapshot.stackStart), &region, sizeof(region))) Fail("VirtualQueryEx");
        if (region.State != MEM_COMMIT) throw std::runtime_error("UI stack region is not committed");
        snapshot.regionStart = reinterpret_cast<DWORD64>(region.BaseAddress);
        snapshot.regionEnd = snapshot.regionStart + region.RegionSize;
        if (snapshot.stackStart < snapshot.regionStart || snapshot.stackStart >= snapshot.regionEnd)
            throw std::runtime_error("UI stack pointer is outside its queried region");
        const auto available = snapshot.regionEnd - snapshot.stackStart;
        const auto wanted = static_cast<SIZE_T>(std::min<DWORD64>(StackCapacity, available));
        const BOOL copied = ReadProcessMemory(process.value, reinterpret_cast<LPCVOID>(snapshot.stackStart),
                                              snapshot.bytes.data(), wanted, &snapshot.copied);
        if (!copied && snapshot.copied == 0) Fail("Read stack snapshot");
        snapshot.truncated = available > snapshot.copied;
        suspended.Resume();
    }
    const auto resumed = GetTickCount64();
    std::cout << "{\"kind\":\"native_snapshot\",\"pid\":" << pid << ",\"thread_id\":" << target.thread
        << ",\"window\":" << Quote(Hex(reinterpret_cast<DWORD64>(target.window)))
        << ",\"resumed_before_unwind\":true,\"suspended_ms\":" << resumed - captureStarted
        << ",\"prior_suspend_count\":" << priorSuspendCount << ",\"stack_bytes\":" << snapshot.copied
        << ",\"stack_truncated\":" << (snapshot.truncated ? "true" : "false")
        << ",\"ip\":" << Quote(Hex(snapshot.context.Rip)) << ",\"sp\":" << Quote(Hex(snapshot.context.Rsp))
        << "}\n" << std::flush;
    // Only now initialize DbgHelp. Symbol loading/unwinding cannot leave the UI
    // suspended if the external watchdog terminates this diagnostic helper.
    currentSnapshot = &snapshot;
    Symbols symbols(process.value);
    CONTEXT context = snapshot.context;
    STACKFRAME64 frame{};
    frame.AddrPC.Offset = context.Rip; frame.AddrPC.Mode = AddrModeFlat;
    frame.AddrStack.Offset = context.Rsp; frame.AddrStack.Mode = AddrModeFlat;
    frame.AddrFrame.Offset = context.Rbp; frame.AddrFrame.Mode = AddrModeFlat;
    std::vector<std::pair<DWORD64, DWORD64>> frames;
    std::string stop = FrameProblem(process.value, snapshot, context.Rip, context.Rsp);
    if (stop.empty()) {
        frames.emplace_back(context.Rip, context.Rsp);
        stop = "frame limit";
    } else EmitRejected(context.Rip, context.Rsp, stop);
    for (size_t step = 0; !frames.empty() && step < FrameLimit; ++step) {
        if (GetTickCount64() - resumed >= WalkBudgetMs) { stop = "unwind time limit"; break; }
        if (!StackWalk64(IMAGE_FILE_MACHINE_AMD64, process.value, thread.value, &frame, &context,
                         ReadSnapshot, SymFunctionTableAccess64, SymGetModuleBase64, nullptr)) {
            stop = "unwind unavailable (including dynamic/JIT or truncated stack)"; break;
        }
        if (!frame.AddrPC.Offset) { stop = "end"; break; }
        const auto next = std::make_pair(frame.AddrPC.Offset, frame.AddrStack.Offset);
        if (next == frames.back()) {
            if (step == 0) continue;
            stop = "repeated frame"; break;
        }
        const auto problem = FrameProblem(process.value, snapshot, next.first, next.second, frames.back().second);
        if (!problem.empty()) {
            stop = problem; EmitRejected(next.first, next.second, problem); break;
        }
        frames.push_back(next);
        if (frames.size() >= FrameLimit) break;
    }
    size_t resolved = 0;
    for (size_t index = 0; index < frames.size(); ++index) {
        const bool resolve = GetTickCount64() - resumed < WalkBudgetMs;
        EmitFrame(process.value, index, frames[index].first, frames[index].second, resolve);
        if (resolve) ++resolved;
    }
    std::cout << "{\"kind\":\"native_summary\",\"complete\":" << (stop == "end" ? "true" : "false")
        << ",\"stop_reason\":" << Quote(stop) << ",\"raw_frame_count\":" << frames.size()
        << ",\"resolved_frame_count\":" << resolved << ",\"total_ms\":" << GetTickCount64() - started
        << ",\"symbol_server\":false}\n";
    return 0;
}
} // namespace

int wmain(int argc, wchar_t** argv) {
    try {
        if (!EnvTrue(L"GITHUB_ACTIONS") || !EnvTrue(L"RELIC_PERF_DIAGNOSTIC"))
            throw std::runtime_error("Native stack capture is restricted to explicit CI diagnostics");
        if (argc != 3 || std::wstring(argv[1]) != L"--pid")
            throw std::runtime_error("Usage: Relic.NativeStack.exe --pid <owned native PID>");
        size_t consumed = 0;
        const auto value = std::stoul(argv[2], &consumed);
        if (!value || consumed != std::wstring(argv[2]).size()) throw std::runtime_error("Invalid target PID");
        return Capture(static_cast<DWORD>(value));
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
