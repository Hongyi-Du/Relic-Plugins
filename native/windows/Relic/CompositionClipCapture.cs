using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using System.Numerics;
using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Relic;

public sealed partial class MainWindow
{
    private JsonObject CaptureCompositionClip(FrameworkElement owner, JsonObject ownerNode)
    {
        // GetElementVisual is not a read-only way to discover an existing visual.
        // In the shipped WinUI source, EnsureHandOffVisual can create a visual,
        // attach transform listeners and dirty the composition tree. Doing that
        // between the PNG and UIA reads changes the object being measured.
        // https://github.com/microsoft/microsoft-ui-xaml/blob/da699b040bddc2a6adf660512a7c6db8a96bfbe3/src/dxaml/xcp/core/core/elements/uielement.cpp#L7213
        // Only the toolbar logo currently retains its actual production
        // backing-Visual binding. Hand-in shadow visuals do not prove that
        // binding for other controls; their measurement stays unknown.
        var evidence = new JsonObject
        {
            ["source"] = "Actual XAML owner; backing Visual not read during authoritative capture",
            ["status"] = "not-measured", ["owner_id"] = ownerNode["id"]?.DeepClone(),
            ["owner_runtime_type"] = owner.GetType().FullName, ["owner_type"] = owner.GetType().Name,
            ["owner_is_loaded"] = owner.IsLoaded, ["observed_at_utc"] = DateTimeOffset.UtcNow.ToString("O"),
            ["owner_local_bounds"] = ownerNode["local_bounds"]?.DeepClone(),
            ["owner_to_window"] = ownerNode["transform"]?.DeepClone(),
            ["xaml_clip_present"] = owner.Clip != null,
            ["backing_visual_read"] = false, ["production_backing_visual_binding_available"] = false,
            ["before"] = null, ["after"] = null, ["binding"] = null, ["properties_stable"] = null,
            ["reason"] = "No production-retained backing Visual/owner binding is available. GetElementVisual may create handoff state and is not called in the authoritative capture window; Composition clip presence and geometry remain unmeasured.",
            ["quantity"] = "Actual XAML owner identity and separately retained UIElement.Clip evidence only; no backing Visual clip observation",
            ["presentation_identity_proven"] = false
        };
        if (!ReferenceEquals(owner, toolbarLogoBackingOwner) || toolbarLogoBackingVisual == null)
            return evidence;
        evidence["source"] = "production-retained backing Visual from ClipToolbarLogo";
        evidence["backing_visual_read"] = true;
        evidence["production_backing_visual_binding_available"] = true;
        evidence["reason"] = null;
        evidence["status"] = "incomplete";
        evidence["quantity"] = "Actual retained production Composition property getters; not compositor-sampled or final-PNG clipping coverage";
        try
        {
            var visual = toolbarLogoBackingVisual;
            var revision = toolbarLogoClipRevision;
            var boundRoot = toolbarLogoBackingRoot;
            var clip = visual.Clip;
            var geometry = (clip as CompositionGeometricClip)?.Geometry;
            var before = RetainedClipSnapshot(visual, clip);
            evidence["before"] = before;
            var afterVisual = toolbarLogoBackingVisual;
            var afterClip = afterVisual?.Clip;
            var afterGeometry = (afterClip as CompositionGeometricClip)?.Geometry;
            var after = afterVisual == null ? null : RetainedClipSnapshot(afterVisual, afterClip);
            evidence["after"] = after;
            evidence["production_binding"] = new JsonObject
            {
                ["source"] = "Actual ClipToolbarLogo assignment and retained owner/root/Visual fields",
                ["owner_same_object"] = ReferenceEquals(owner, toolbarLogoBackingOwner),
                ["owner_is_current_logo"] = ReferenceEquals(owner, toolbarLogo),
                ["same_xaml_root"] = boundRoot != null && ReferenceEquals(owner.XamlRoot, boundRoot)
                    && ReferenceEquals(toolbarLogoBackingRoot, boundRoot),
                ["owner_is_loaded_after"] = owner.IsLoaded,
                ["revision_before"] = revision, ["revision_after"] = toolbarLogoClipRevision,
                ["visual_same_retained_object"] = ReferenceEquals(visual, afterVisual),
                ["clip_is_installed_production_object"] = clip != null && toolbarLogoClip != null
                    && RetainedClipSameObject(clip, toolbarLogoClip),
                ["geometry_is_installed_production_object"] = geometry != null && toolbarLogoClipGeometry != null
                    && RetainedClipSameObject(geometry, toolbarLogoClipGeometry),
                ["read_only"] = true
            };
            evidence["binding"] = new JsonObject
            {
                ["source"] = "actual IUnknown identity comparison; acquired references released in finally",
                ["visual_same_object_after"] = afterVisual != null && RetainedClipSameObject(visual, afterVisual),
                ["clip_same_object_after"] = clip == null ? afterClip == null : afterClip != null && RetainedClipSameObject(clip, afterClip),
                ["geometry_same_object_after"] = geometry == null ? afterGeometry == null : afterGeometry != null && RetainedClipSameObject(geometry, afterGeometry)
            };
            evidence["properties_stable"] = JsonNode.DeepEquals(before, after);
            evidence["status"] = "measured";
        }
        catch (Exception error)
        {
            evidence["status"] = "failed";
            evidence["failure"] = new JsonObject { ["type"] = error.GetType().FullName,
                ["message"] = error.Message, ["hresult"] = error.HResult };
        }
        return evidence;
    }

    private static JsonObject RetainedClipSnapshot(Visual visual, CompositionClip? clip)
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
                paint["trim_start"] = geometry.TrimStart; paint["trim_end"] = geometry.TrimEnd;
                paint["trim_offset"] = geometry.TrimOffset;
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
        value.M21, value.M22, value.M23, value.M24, value.M31, value.M32, value.M33, value.M34,
        value.M41, value.M42, value.M43, value.M44);
    private static bool RetainedClipSameObject(object first, object second)
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
