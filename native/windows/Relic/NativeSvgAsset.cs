using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;
using Windows.Storage.Streams;

namespace Relic;

// The actual production Image decodes these exact packaged bytes. Its capture
// receipt describes source/content identity, not proof of final presentation.
internal sealed class NativeSvgAsset
{
    private static readonly ConditionalWeakTable<Image, NativeSvgAsset> Assets = new();
    private readonly Image image;
    private readonly SvgImageSource source = new();
    private readonly string relativePath;
    private byte[]? bytes;
    private Task? loading;
    private string phase = "not-started";
    private SvgImageSourceLoadStatus? status;
    private string? sourceFailure, imageFailure, exceptionType, exceptionMessage;
    private int? exceptionHresult;
    private int sourceOpened, imageOpened;
    private uint? streamBytesWritten;
    private ulong? streamLength;

    private NativeSvgAsset(Image image, string relativePath)
    {
        this.image = image; this.relativePath = relativePath;
        source.Opened += (_, _) => sourceOpened++;
        source.OpenFailed += (_, args) => sourceFailure = args.Status.ToString();
        image.ImageOpened += (_, _) => imageOpened++;
        image.ImageFailed += (_, args) => imageFailure = args.ErrorMessage;
        image.Source = source;
        image.Loaded += (_, _) => loading ??= LoadAsync();
    }

    internal static void LoadPackagedInto(Image image, string relativePath)
        => Assets.Add(image, new NativeSvgAsset(image, relativePath));

    private async Task LoadAsync()
    {
        try
        {
            phase = "reading-packaged-bytes";
            bytes = await File.ReadAllBytesAsync(Path.Combine(AppContext.BaseDirectory, relativePath));
            using var stream = new InMemoryRandomAccessStream();
            using (var writer = new DataWriter(stream))
            {
                writer.WriteBytes(bytes);
                streamBytesWritten = await writer.StoreAsync();
                writer.DetachStream();
            }
            streamLength = stream.Size; stream.Seek(0);
            phase = "decoding-actual-source";
            status = await source.SetSourceAsync(stream);
            phase = status == SvgImageSourceLoadStatus.Success ? "decoded" : "failed";
        }
        catch (Exception ex)
        {
            phase = "failed"; exceptionType = ex.GetType().FullName;
            exceptionMessage = ex.Message; exceptionHresult = ex.HResult;
        }
    }

    private bool SameSourceIdentity()
    {
        if (image.Source == null) return false;
        IntPtr bound = IntPtr.Zero, loaded = IntPtr.Zero, boundIdentity = IntPtr.Zero, loadedIdentity = IntPtr.Zero;
        try
        {
            bound = WinRT.MarshalInspectable<object>.FromManaged(image.Source);
            loaded = WinRT.MarshalInspectable<object>.FromManaged(source);
            var iid = new Guid("00000000-0000-0000-c000-000000000046");
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(bound, ref iid, out boundIdentity));
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(loaded, ref iid, out loadedIdentity));
            return boundIdentity == loadedIdentity;
        }
        finally
        {
            if (boundIdentity != IntPtr.Zero) Marshal.Release(boundIdentity);
            if (loadedIdentity != IntPtr.Zero) Marshal.Release(loadedIdentity);
            if (bound != IntPtr.Zero) Marshal.Release(bound);
            if (loaded != IntPtr.Zero) Marshal.Release(loaded);
        }
    }

    internal static JsonObject? Capture(Image candidate)
    {
        if (!Assets.TryGetValue(candidate, out var asset)) return null;
        bool? sameIdentity = null; JsonObject? identityError = null;
        try { sameIdentity = asset.SameSourceIdentity(); }
        catch (Exception ex)
        {
            identityError = new JsonObject { ["exception_type"] = ex.GetType().FullName,
                ["message"] = ex.Message, ["hresult"] = ex.HResult };
        }
        var exactStream = asset.bytes != null && asset.streamBytesWritten == asset.bytes.Length
            && asset.streamLength == (ulong)asset.bytes.Length;
        return new JsonObject
        {
            ["source"] = "Actual production Image and SvgImageSource.SetSourceAsync packaged-byte binding",
            ["registered_image_same_object"] = ReferenceEquals(candidate, asset.image),
            ["bound_source_same_managed_object"] = ReferenceEquals(candidate.Source, asset.source),
            ["bound_source_same_com_identity"] = sameIdentity, ["identity_error"] = identityError,
            ["resource_path"] = asset.relativePath, ["mime_type"] = "image/svg+xml",
            ["content_encoding"] = "base64", ["content_bytes"] = asset.bytes == null ? null : Convert.ToBase64String(asset.bytes),
            ["byte_length"] = asset.bytes?.Length, ["stream_bytes_written"] = asset.streamBytesWritten,
            ["stream_length"] = asset.streamLength, ["exact_byte_stream"] = exactStream,
            ["phase"] = asset.phase, ["load_status"] = asset.status?.ToString(),
            ["source_opened_events"] = asset.sourceOpened, ["image_opened_events"] = asset.imageOpened,
            ["source_failed_status"] = asset.sourceFailure, ["image_failed_message"] = asset.imageFailure,
            ["exception_type"] = asset.exceptionType, ["exception_message"] = asset.exceptionMessage,
            ["exception_hresult"] = asset.exceptionHresult, ["image_is_loaded"] = candidate.IsLoaded,
            ["uri_source"] = asset.source.UriSource?.ToString(),
            ["rasterize_width"] = double.IsFinite(asset.source.RasterizePixelWidth) ? asset.source.RasterizePixelWidth : null,
            ["rasterize_height"] = double.IsFinite(asset.source.RasterizePixelHeight) ? asset.source.RasterizePixelHeight : null,
            ["rasterize_width_is_auto"] = double.IsNaN(asset.source.RasterizePixelWidth),
            ["rasterize_height_is_auto"] = double.IsNaN(asset.source.RasterizePixelHeight),
            ["content_binding_complete"] = ReferenceEquals(candidate, asset.image) && sameIdentity == true && exactStream
                && asset.phase == "decoded" && asset.status == SvgImageSourceLoadStatus.Success
                && asset.sourceFailure == null && asset.imageFailure == null,
            ["quantity"] = "Exact bytes submitted to the currently bound source and its actual decode status; final screenshot pixels remain independent"
        };
    }
}
