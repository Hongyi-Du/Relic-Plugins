using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using static Relic.NativeLabelInterop;

namespace Relic;

// CI observes the actual current SurfaceImageSource target between its original
// draw and EndDraw. This is a resource copy, never another text layout or render.
// Raw surface pixels do not establish their contribution to the desktop PNG.
internal sealed class NativeLabelReadback
{
    internal static bool Enabled => CaptureDiagnostics;

    internal long LayoutRevision { get; }
    internal long SurfaceRevision { get; }
    internal long DrawOrdinal { get; }
    private readonly JsonObject evidence;
    private readonly JsonArray stages = new();
    private byte[]? pixels;
    private static long nextProbeId;
    private readonly long probeId = Interlocked.Increment(ref nextProbeId);
    private FileStream? journal;
    private string? lastSuccessfulApi;
    private long journalTicks;
    private int journalWrites;

    private NativeLabelReadback(long layoutRevision, long surfaceRevision, long drawOrdinal)
    {
        LayoutRevision = layoutRevision; SurfaceRevision = surfaceRevision; DrawOrdinal = drawOrdinal;
        evidence = new JsonObject
        {
            ["source"] = "Actual SurfaceImageSource BeginDraw target copied after production glyph drawing and before SurfaceImageSource.EndDraw",
            ["status"] = "incomplete", ["layout_revision"] = layoutRevision, ["surface_revision"] = surfaceRevision,
            ["draw_ordinal"] = drawOrdinal, ["qpc_frequency"] = Stopwatch.Frequency,
            ["probe_id"] = probeId,
            ["started_qpc"] = Stopwatch.GetTimestamp(), ["completed_qpc"] = null, ["stages"] = stages,
            ["raw_sidecar"] = null, ["metadata_sidecar"] = null, ["surface_end_draw_hresult"] = null,
            ["presentation_identity_proven"] = false,
            ["quantity"] = "Unmodified premultiplied surface texels. No claim of final window-pixel contribution or presented-frame identity."
        };
    }

    internal static NativeLabelReadback Observe(IntPtr actualContext, Point offset, int width, int height,
        long layoutRevision, long surfaceRevision, long drawOrdinal)
    {
        if (!Enabled) throw new InvalidOperationException("NativeLabel surface readback is CI-only");
        var result = new NativeLabelReadback(layoutRevision, surfaceRevision, drawOrdinal);
        result.Read(actualContext, offset, width, height);
        return result;
    }

    internal JsonObject Snapshot() => evidence.DeepClone().AsObject();

    internal void ObserveEndDraw(int hr)
    {
        evidence["surface_end_draw_hresult"] = hr;
        evidence["surface_end_draw_hresult_hex"] = Hex(hr);
        evidence["surface_submission_succeeded"] = hr >= 0;
        try
        {
            OpenJournal();
            Journal("surface-submission", new JsonObject { ["api"] = "ISurfaceImageSourceNativeWithD2D/EndDraw",
                ["hresult"] = hr, ["hresult_hex"] = Hex(hr), ["status"] = hr >= 0 ? "completed" : "error" });
        }
        catch (Exception ex) { Failure(ex); }
        finally { CloseJournal(); }
        // Readback remains a measurement of the pre-submit surface even when
        // submission fails; it must not become presented-pixel evidence.
    }

    private void Read(IntPtr context, Point offset, int width, int height)
    {
        IntPtr target = IntPtr.Zero, bitmap = IntPtr.Zero, staging = IntPtr.Zero, colorContext = IntPtr.Zero;
        var mapped = false;
        evidence["copy_extent_pixels"] = new JsonObject { ["x"] = offset.X, ["y"] = offset.Y, ["width"] = width, ["height"] = height };
        try
        {
            OpenJournal();
            Journal("read-start", evidence["copy_extent_pixels"]!.AsObject());
            Call("ID2D1DeviceContext/GetTarget", () => Method<GetTargetImage>(context, 75)(context, out target));
            if (target == IntPtr.Zero) throw new InvalidOperationException("The actual production device context has no target image");
            evidence["target_process_identity"] = Identity(target);
            var bitmapId = Bitmap1;
            HResult("IUnknown/QueryInterface/ID2D1Bitmap1", () => Marshal.QueryInterface(target, ref bitmapId, out bitmap));
            SizeU size = default;
            Call("ID2D1Bitmap/GetPixelSize", () => Method<GetBitmapPixelSize>(bitmap, 5)(bitmap, out size));
            PixelFormat format = default;
            Call("ID2D1Bitmap/GetPixelFormat", () => Method<GetBitmapPixelFormat>(bitmap, 6)(bitmap, out format));
            float dpiX = 0, dpiY = 0;
            Call("ID2D1Bitmap/GetDpi", () => Method<GetBitmapDpi>(bitmap, 7)(bitmap, out dpiX, out dpiY));
            var options = Call("ID2D1Bitmap1/GetOptions", () => Method<GetUInt>(bitmap, 12)(bitmap));
            Call("ID2D1Bitmap1/GetColorContext", () => Method<GetBitmapColorContext>(bitmap, 11)(bitmap, out colorContext));
            evidence["target"] = new JsonObject
            {
                ["width_pixels"] = size.Width, ["height_pixels"] = size.Height,
                ["dxgi_format"] = format.Format, ["alpha_mode"] = format.AlphaMode,
                ["dpi_x"] = dpiX, ["dpi_y"] = dpiY, ["bitmap_options"] = options,
                ["color_context_process_identity"] = colorContext == IntPtr.Zero ? null : Identity(colorContext)
            };
            Journal("target-properties", evidence["target"]!.AsObject());
            // The source format is observed, not inferred from the D3D device.
            // This first reader decodes only actual 8-bit premultiplied BGRA.
            if (format.Format is not (87 or 91) || format.AlphaMode != 1)
                throw new NotSupportedException("Actual target is not premultiplied BGRA8: DXGI=" + format.Format + ", alpha=" + format.AlphaMode);
            if (width <= 0 || height <= 0 || offset.X < 0 || offset.Y < 0
                || (long)offset.X + width > size.Width || (long)offset.Y + height > size.Height)
                throw new InvalidOperationException("Actual BeginDraw update rectangle is outside the returned target bitmap");
            if (!float.IsFinite(dpiX) || !float.IsFinite(dpiY) || dpiX <= 0 || dpiY <= 0)
                throw new InvalidOperationException("Actual target DPI is not finite and positive");

            var properties = new BitmapProperties1
            {
                PixelFormat = format, DpiX = dpiX, DpiY = dpiY,
                Options = 0x2 | 0x4, // CANNOT_DRAW | CPU_READ; never TARGET.
                ColorContext = colorContext
            };
            var extent = new SizeU { Width = checked((uint)width), Height = checked((uint)height) };
            HResult("ID2D1DeviceContext/CreateBitmap/CPU_READ", () => Method<CreateReadbackBitmap>(context, 57)(context, extent, IntPtr.Zero, 0, ref properties, out staging));
            if (staging == IntPtr.Zero) throw new InvalidOperationException("CreateBitmap returned no readback bitmap");
            var destination = new PointU();
            var rectangle = new RectU { Left = checked((uint)offset.X), Top = checked((uint)offset.Y),
                Right = checked((uint)(offset.X + width)), Bottom = checked((uint)(offset.Y + height)) };
            HResult("ID2D1Bitmap/CopyFromBitmap/actual-target", () => Method<CopyBitmapPixels>(staging, 8)(staging, ref destination, bitmap, ref rectangle));
            MappedRect memory = default;
            HResult("ID2D1Bitmap1/Map/READ", () => Method<MapBitmapPixels>(staging, 14)(staging, 1, out memory)); mapped = true;
            var rowBytes = checked(width * 4);
            evidence["mapped_pitch_bytes"] = memory.Pitch;
            evidence["stored_row_bytes"] = rowBytes;
            evidence["channel_order"] = "BGRA";
            evidence["alpha_representation"] = "premultiplied; original alpha bytes preserved";
            evidence["dxgi_format_name"] = format.Format == 87 ? "DXGI_FORMAT_B8G8R8A8_UNORM" : "DXGI_FORMAT_B8G8R8A8_UNORM_SRGB";
            evidence["row_layout"] = "Original width*4 bytes per row copied in mapped row order; GPU pitch padding is not pixel content and is not exported";
            if (memory.Bits == IntPtr.Zero || memory.Pitch < rowBytes)
                throw new InvalidOperationException("Map returned no pixels or a pitch smaller than the actual BGRA row");
            var raw = new byte[checked(rowBytes * height)];
            Call("Marshal/Copy/actual-mapped-pixel-rows", () =>
            {
                for (var row = 0; row < height; row++)
                    Marshal.Copy(IntPtr.Add(memory.Bits, checked(row * (int)memory.Pitch)), raw, row * rowBytes, rowBytes);
            });
            pixels = raw; evidence["pixel_byte_count"] = raw.Length;
            evidence["status"] = "surface-pixels-read";
        }
        catch (Exception ex) { Failure(ex); }
        finally
        {
            if (mapped)
            {
                try { HResult("ID2D1Bitmap1/Unmap", () => Method<UnmapBitmapPixels>(staging, 15)(staging)); }
                catch (Exception ex) { Failure(ex); }
            }
            try
            {
                ReleaseObserved("staging-bitmap", ref staging); ReleaseObserved("color-context", ref colorContext);
                ReleaseObserved("target-bitmap", ref bitmap); ReleaseObserved("target-image", ref target);
                evidence["completed_qpc"] = Stopwatch.GetTimestamp();
                Journal("read-finished", new JsonObject { ["status"] = evidence["status"]?.DeepClone(),
                    ["failures"] = evidence["failures"]?.DeepClone(), ["pixel_byte_count"] = pixels?.Length });
            }
            catch (Exception ex) { Failure(ex); }
            finally { CloseJournal(); }
        }
    }

    internal JsonObject Write(string directory, string caseId, int labelIndex, bool isCurrent)
    {
        if (!Enabled) throw new InvalidOperationException("NativeLabel readback export is CI-only");
        if (string.IsNullOrWhiteSpace(caseId) || caseId.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || labelIndex < 0)
            throw new ArgumentException("Readback export requires an actual case filename and label index");
        var stem = caseId + ".native-label-" + labelIndex + "-layout-" + LayoutRevision + "-surface-" + SurfaceRevision + "-draw-" + DrawOrdinal;
        evidence["is_current_draw_at_export"] = isCurrent;
        evidence["case_id"] = caseId; evidence["capture_label_index"] = labelIndex;
        Directory.CreateDirectory(directory);
        if (pixels != null)
        {
            var name = stem + ".bgra";
            File.WriteAllBytes(Path.Combine(directory, name), pixels);
            evidence["raw_sidecar"] = name;
        }
        evidence["metadata_sidecar"] = stem + ".json";
        File.WriteAllText(Path.Combine(directory, stem + ".json"), evidence.ToJsonString(new JsonSerializerOptions(JsonSerializerOptions.Default) { WriteIndented = true }), new UTF8Encoding(false));
        return Snapshot();
    }

    private string Identity(IntPtr value)
    {
        var unknown = new Guid("00000000-0000-0000-c000-000000000046"); IntPtr identity = IntPtr.Zero;
        try
        {
            HResult("IUnknown/QueryInterface/IUnknown", () => Marshal.QueryInterface(value, ref unknown, out identity));
            return identity.ToInt64().ToString("X", CultureInfo.InvariantCulture);
        }
        finally { ReleaseObserved("identity", ref identity); }
    }

    private void ReleaseObserved(string name, ref IntPtr value)
    {
        if (value == IntPtr.Zero) return;
        var owned = value; value = IntPtr.Zero;
        Call("IUnknown/Release/" + name, () => Marshal.Release(owned));
    }

    private void OpenJournal()
    {
        if (!Enabled) throw new InvalidOperationException("NativeLabel readback journal is CI-only");
        var manifest = Path.GetFullPath(Environment.GetEnvironmentVariable("RELIC_VISUAL_MANIFEST")!);
        var path = Path.Combine(Path.GetDirectoryName(manifest)!, "native-label-readback.progress.jsonl");
        // One compact append-only file per actual case/process. Do not repeatedly
        // serialize every label's accumulated evidence, nor create per-stage files.
        journal = new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.Read,
            bufferSize: 4096, options: FileOptions.None);
        evidence["journal_file"] = Path.GetFileName(path);
    }

    private void Journal(string phase, JsonObject details)
    {
        if (journal == null) throw new InvalidOperationException("NativeLabel readback journal is not open");
        var started = Stopwatch.GetTimestamp();
        var entry = new JsonObject
        {
            ["process_id"] = Environment.ProcessId, ["probe_id"] = probeId,
            ["layout_revision"] = LayoutRevision, ["surface_revision"] = SurfaceRevision, ["draw_ordinal"] = DrawOrdinal,
            ["qpc"] = started, ["qpc_frequency"] = Stopwatch.Frequency, ["phase"] = phase,
            ["last_successful_api"] = lastSuccessfulApi,
            ["pending_api"] = phase == "api-start" ? details["api"]?.DeepClone() : null,
            ["details"] = details.DeepClone(), ["presentation_identity_proven"] = false
        };
        var bytes = Encoding.UTF8.GetBytes(entry.ToJsonString() + "\n");
        journal.Write(bytes);
        // Hand the complete prefix to the OS BEFORE entering native code. A fatal
        // process AccessViolation skips managed finally; it does not discard the
        // OS file cache. No device-level flush is needed for that failure mode.
        // Never turn a journal write failure into a pass.
        journal.Flush();
        journalTicks += Stopwatch.GetTimestamp() - started; journalWrites++;
    }

    private void CloseJournal()
    {
        journal?.Dispose(); journal = null;
        evidence["journal_write_count"] = journalWrites;
        evidence["journal_io_ms"] = journalTicks * 1000.0 / Stopwatch.Frequency;
    }

    private static string Hex(int value) => "0x" + unchecked((uint)value).ToString("X8", CultureInfo.InvariantCulture);
    private void Failure(Exception error)
    {
        evidence["status"] = "error";
        if (evidence["failures"] is not JsonArray errors) { errors = new JsonArray(); evidence["failures"] = errors; }
        errors.Add(new JsonObject { ["exception_type"] = error.GetType().FullName, ["hresult"] = error.HResult,
            ["hresult_hex"] = Hex(error.HResult), ["message"] = error.Message, ["exception"] = error.ToString() });
    }

    private void HResult(string api, Func<int> call)
    {
        var stage = new JsonObject { ["api"] = api, ["started_qpc"] = Stopwatch.GetTimestamp(), ["status"] = "started" };
        stages.Add(stage);
        Journal("api-start", stage);
        try
        {
            var hr = call(); stage["hresult"] = hr; stage["hresult_hex"] = Hex(hr); Check(hr);
            stage["status"] = "completed"; lastSuccessfulApi = api;
        }
        catch (Exception ex) { stage["status"] = "error"; stage["exception"] = ex.ToString(); throw; }
        finally { stage["completed_qpc"] = Stopwatch.GetTimestamp(); Journal("api-finished", stage); }
    }

    private T Call<T>(string api, Func<T> call)
    {
        var stage = new JsonObject { ["api"] = api, ["started_qpc"] = Stopwatch.GetTimestamp(),
            ["status"] = "started", ["hresult"] = null, ["return_kind"] = "Native getter returns a value or void, not HRESULT" };
        stages.Add(stage);
        Journal("api-start", stage);
        try { var value = call(); stage["status"] = "completed"; lastSuccessfulApi = api; return value; }
        catch (Exception ex) { stage["status"] = "error"; stage["exception"] = ex.ToString(); throw; }
        finally { stage["completed_qpc"] = Stopwatch.GetTimestamp(); Journal("api-finished", stage); }
    }
    private void Call(string api, Action call) => Call(api, () => { call(); return true; });
}
