using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Hosting;
using System.Numerics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private static JsonObject CaptureCompositionClip(FrameworkElement owner, JsonObject ownerNode)
    {
        var evidence = new JsonObject
        {
            ["source"] = "actual ElementCompositionPreview.GetElementVisual(owner).Clip",
            ["status"] = "incomplete", ["owner_id"] = ownerNode["id"]?.DeepClone(),
            ["owner_runtime_type"] = owner.GetType().FullName, ["owner_type"] = owner.GetType().Name, ["owner_is_loaded"] = owner.IsLoaded,
            ["sample_started_utc"] = DateTimeOffset.UtcNow.ToString("O"),
            ["owner_local_bounds"] = ownerNode["local_bounds"]?.DeepClone(),
            ["owner_to_window"] = ownerNode["transform"]?.DeepClone(),
            ["xaml_clip_present"] = owner.Clip != null,
            ["quantity"] = "Actual Composition object property getters; not a compositor-sampled or final-PNG clipping mask",
            ["presentation_identity_proven"] = false
        };
        try
        {
            // The returned object backs this exact XAML owner; no name, bounds,
            // child enumeration or expected clip radius identifies the object.
            // https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.xaml.hosting.elementcompositionpreview.getelementvisual
            var visual = ElementCompositionPreview.GetElementVisual(owner);
            var clip = visual.Clip;
            var geometry = (clip as CompositionGeometricClip)?.Geometry;
            var before = CompositionClipSnapshot(visual, clip);
            evidence["before"] = before;
            var afterVisual = ElementCompositionPreview.GetElementVisual(owner);
            var afterClip = afterVisual.Clip;
            var afterGeometry = (afterClip as CompositionGeometricClip)?.Geometry;
            var after = CompositionClipSnapshot(afterVisual, afterClip);
            evidence["after"] = after;
            evidence["binding"] = new JsonObject
            {
                ["source"] = "actual IUnknown identity comparison; acquired references released in finally",
                ["visual_same_object_after"] = CompositionClipSameObject(visual, afterVisual),
                ["clip_same_object_after"] = clip == null ? afterClip == null : afterClip != null && CompositionClipSameObject(clip, afterClip),
                ["geometry_same_object_after"] = geometry == null ? afterGeometry == null : afterGeometry != null && CompositionClipSameObject(geometry, afterGeometry)
            };
            evidence["properties_stable"] = JsonNode.DeepEquals(before, after);
            evidence["status"] = "measured";
        }
        catch (Exception error)
        {
            evidence["status"] = "failed";
            evidence["failure"] = new JsonObject { ["type"] = error.GetType().FullName, ["message"] = error.Message, ["hresult"] = error.HResult };
        }
        evidence["sample_completed_utc"] = DateTimeOffset.UtcNow.ToString("O");
        return evidence;
    }

    private static JsonObject CompositionClipSnapshot(Visual visual, CompositionClip? clip)
    {
        var result = new JsonObject
        {
            ["visual"] = new JsonObject
            {
                ["type"] = visual.GetType().FullName, ["size"] = ClipVector(visual.Size),
                ["offset"] = ClipVector(visual.Offset), ["anchor_point"] = ClipVector(visual.AnchorPoint),
                ["center_point"] = ClipVector(visual.CenterPoint), ["scale"] = ClipVector(visual.Scale),
                ["rotation_angle"] = visual.RotationAngle, ["rotation_axis"] = ClipVector(visual.RotationAxis),
                ["transform_matrix"] = ClipMatrix(visual.TransformMatrix)
            },
            ["clip_present"] = clip != null, ["clip"] = null
        };
        if (clip == null) return result;
        // These are clip-local transform properties, not the owner's XAML matrix.
        // https://learn.microsoft.com/en-us/windows/windows-app-sdk/api/winrt/microsoft.ui.composition.compositionclip
        var value = new JsonObject
        {
            ["type"] = clip.GetType().FullName, ["anchor_point"] = ClipVector(clip.AnchorPoint),
            ["center_point"] = ClipVector(clip.CenterPoint), ["offset"] = ClipVector(clip.Offset),
            ["scale"] = ClipVector(clip.Scale), ["rotation_angle"] = clip.RotationAngle,
            ["transform_matrix"] = ClipMatrix(clip.TransformMatrix)
        };
        result["clip"] = value;
        if (clip is CompositionGeometricClip geometric)
        {
            var geometry = geometric.Geometry;
            var paint = new JsonObject { ["type"] = geometry?.GetType().FullName };
            value["geometry"] = paint;
            if (geometry != null)
            {
                paint["trim_start"] = geometry.TrimStart; paint["trim_end"] = geometry.TrimEnd; paint["trim_offset"] = geometry.TrimOffset;
            }
            if (geometry is CompositionRoundedRectangleGeometry rounded)
            {
                paint["size"] = ClipVector(rounded.Size); paint["offset"] = ClipVector(rounded.Offset);
                paint["corner_radius"] = ClipVector(rounded.CornerRadius);
            }
            else if (geometry is CompositionRectangleGeometry rectangle)
            {
                paint["size"] = ClipVector(rectangle.Size); paint["offset"] = ClipVector(rectangle.Offset);
            }
        }
        else if (clip is InsetClip inset)
            value["insets"] = new JsonArray(inset.LeftInset, inset.TopInset, inset.RightInset, inset.BottomInset);
        return result;
    }

    private static JsonArray ClipVector(Vector2 value) => new(value.X, value.Y);
    private static JsonArray ClipVector(Vector3 value) => new(value.X, value.Y, value.Z);
    private static JsonArray ClipMatrix(Matrix3x2 value) => new(value.M11, value.M12, value.M21, value.M22, value.M31, value.M32);
    private static JsonArray ClipMatrix(Matrix4x4 value) => new(value.M11, value.M12, value.M13, value.M14,
        value.M21, value.M22, value.M23, value.M24, value.M31, value.M32, value.M33, value.M34, value.M41, value.M42, value.M43, value.M44);

    private static bool CompositionClipSameObject(object first, object second)
    {
        IntPtr a = IntPtr.Zero, b = IntPtr.Zero, ai = IntPtr.Zero, bi = IntPtr.Zero;
        try
        {
            a = WinRT.MarshalInspectable<object>.FromManaged(first); b = WinRT.MarshalInspectable<object>.FromManaged(second);
            var iid = new Guid("00000000-0000-0000-c000-000000000046");
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(a, ref iid, out ai));
            Marshal.ThrowExceptionForHR(Marshal.QueryInterface(b, ref iid, out bi));
            return ai == bi;
        }
        finally
        {
            if (ai != IntPtr.Zero) Marshal.Release(ai); if (bi != IntPtr.Zero) Marshal.Release(bi);
            if (a != IntPtr.Zero) Marshal.Release(a); if (b != IntPtr.Zero) Marshal.Release(b);
        }
    }
}
