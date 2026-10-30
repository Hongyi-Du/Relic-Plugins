import AppKit

/// Diagnostic only. This combines real draw ownership, presentation order and
/// every covered screenshot pixel. It does not remove elements from capture.
@MainActor enum NativeOpaqueCoverage {
    private static func id(_ value: AnyObject) -> String { String(describing: ObjectIdentifier(value)) }
    private static func ancestry(_ layer: CALayer) -> [CALayer] {
        var result: [CALayer] = [], next: CALayer? = layer
        while let current = next { result.append(current); next = current.superlayer }
        return result
    }
    static func inspect(target: NSView, screenRect: NSRect, fill: NativeSurfaceFillView,
                        bitmap: NSBitmapImageRep, canvas: NSRect) -> [String: Any] {
        var result: [String: Any] = ["source": "current native fill image, model/presentation order and final raster pixels",
            "target_view": id(target), "fill_view": id(fill), "screen_rect": ElementCapture.box(screenRect),
            "candidate_opaque_cover": false, "changes_visibility": false]
        func fail(_ reason: String) -> [String: Any] { result["reason"] = reason; return result }
        guard target !== fill, let window = target.window, fill.window === window,
              let targetLayer = target.layer, let fillLayer = fill.layer,
              let image = fill.currentOwnedImage(), !screenRect.isNull, !screenRect.isEmpty,
              NativeVisibility.screenClip(fill)?.contains(screenRect) == true,
              NativeVisibility.opacity(fill) == 1 else { return fail("No current same-window opaque fill image covering the entire native rectangle") }
        result["fill_image"] = fill.backingPaintObservation()
        result["target_layer"] = id(targetLayer); result["fill_layer"] = id(fillLayer)
        guard let presentedFill = fillLayer.presentation(),
              (presentedFill.contents as AnyObject?) === image,
              fillLayer.contentsRect == CGRect(x: 0, y: 0, width: 1, height: 1),
              presentedFill.contentsRect == fillLayer.contentsRect,
              presentedFill.contentsGravity == fillLayer.contentsGravity,
              presentedFill.contentsScale == fillLayer.contentsScale else {
            return fail("Presentation contents are not the exact current unmodified fill image")
        }
        let targets = ancestry(targetLayer), fills = ancestry(fillLayer)
        guard let common = targets.first(where: { candidate in fills.contains(where: { $0 === candidate }) }),
              let ti = targets.firstIndex(where: { $0 === common }), ti > 0,
              let fi = fills.firstIndex(where: { $0 === common }), fi > 0 else {
            return fail("No distinct native sibling branches in the same layer tree")
        }
        let targetBranch = targets[ti - 1], fillBranch = fills[fi - 1]
        let siblings = common.sublayers ?? []
        guard let targetIndex = siblings.firstIndex(where: { $0 === targetBranch }),
              let fillIndex = siblings.firstIndex(where: { $0 === fillBranch }),
              fillBranch.zPosition > targetBranch.zPosition || fillBranch.zPosition == targetBranch.zPosition && fillIndex > targetIndex else {
            return fail("The actual fill branch is not in front of the target branch")
        }
        var visited = Set<ObjectIdentifier>(), layerEvidence: [[String: Any]] = []
        let local = fill.convert(window.convertFromScreen(screenRect), from: nil)
        for layer in targets + fills where visited.insert(ObjectIdentifier(layer)).inserted {
            guard let presentation = layer.presentation(), (presentation.model() as AnyObject) === layer,
                  layer.bounds == presentation.bounds, layer.position == presentation.position,
                  layer.anchorPoint == presentation.anchorPoint, layer.anchorPointZ == 0, presentation.anchorPointZ == 0,
                  layer.zPosition == presentation.zPosition, layer.opacity == presentation.opacity,
                  layer.isHidden == presentation.isHidden,
                  layer.isGeometryFlipped == presentation.isGeometryFlipped,
                  CATransform3DIsIdentity(layer.transform), CATransform3DIsIdentity(presentation.transform),
                  CATransform3DIsIdentity(layer.sublayerTransform), CATransform3DIsIdentity(presentation.sublayerTransform),
                  (layer.animationKeys() ?? []).isEmpty, (presentation.animationKeys() ?? []).isEmpty,
                  layer.mask == nil, presentation.mask == nil,
                  layer.compositingFilter == nil, presentation.compositingFilter == nil,
                  (layer.filters ?? []).isEmpty, (presentation.filters ?? []).isEmpty,
                  (layer.backgroundFilters ?? []).isEmpty, (presentation.backgroundFilters ?? []).isEmpty else {
                result["unmeasured_layer"] = NativeLayerOrder.observation(layer)
                return fail("Layer presentation, animation, transforms, masks or effects are not proven stable")
            }
            if fills.contains(where: { $0 === layer }) {
                guard !layer.isHidden, layer.opacity == 1,
                      layer.masksToBounds == presentation.masksToBounds else { return fail("Fill ancestry is hidden, translucent or has a changing clip") }
                if layer.masksToBounds && !layer.bounds.contains(fillLayer.convert(local, to: layer)) {
                    return fail("A real ancestor bounds clip cuts the covered rectangle")
                }
            }
            let modelChildren = (layer.sublayers ?? []).map(ObjectIdentifier.init)
            let presentedChildren = (presentation.sublayers ?? []).map { ObjectIdentifier($0.model() as AnyObject) }
            guard modelChildren == presentedChildren else { return fail("Presentation child order differs from the current model order") }
            layerEvidence.append(["layer": id(layer), "presentation": id(presentation), "ordered_children": (layer.sublayers ?? []).map(id),
                "z_position": layer.zPosition, "opacity": layer.opacity, "masks_to_bounds": layer.masksToBounds])
        }
        result["layer_chain"] = layerEvidence
        result["common_ancestor"] = id(common)
        result["branches"] = ["target": id(targetBranch), "fill": id(fillBranch), "target_index": targetIndex, "fill_index": fillIndex]
        // A later custom compositing filter could reveal lower content. Reject
        // that entire native tree instead of assuming source-over everywhere.
        func hasSpecialBlend(_ layer: CALayer) -> Bool {
            layer.compositingFilter != nil || layer.presentation()?.compositingFilter != nil
                || (layer.sublayers ?? []).contains(where: hasSpecialBlend)
        }
        guard let root = fills.last, !hasSpecialBlend(root) else { return fail("The native tree includes an unmeasured compositing filter") }
        guard image.bitsPerComponent == 8, image.bitsPerPixel == 32,
              image.alphaInfo == .premultipliedLast,
              image.bitmapInfo.intersection(.byteOrderMask) == .byteOrder32Big,
              let data = image.dataProvider?.data, let bytes = CFDataGetBytePtr(data),
              CFDataGetLength(data) >= image.bytesPerRow * image.height else {
            return fail("Owned fill image is not the measured 8-bit RGBA buffer")
        }
        let rect = ElementCapture.topLeft(screenRect, in: canvas)
        let x0 = Int(floor(rect.minX)), y0 = Int(floor(rect.minY)), x1 = Int(ceil(rect.maxX)), y1 = Int(ceil(rect.maxY))
        guard x0 >= 0, y0 >= 0, x1 <= bitmap.pixelsWide, y1 <= bitmap.pixelsHigh else { return fail("Rectangle extends outside the captured raster") }
        let scale = fillLayer.contentsScale
        var count = 0
        for y in y0..<y1 { for x in x0..<x1 {
            let point = NSPoint(x: canvas.minX + CGFloat(x) + 0.5, y: canvas.maxY - CGFloat(y) - 0.5)
            let at = fill.convert(window.convertPoint(fromScreen: point), from: nil)
            let px = Int(floor((at.x - fill.bounds.minX) * scale)), py = Int(floor((at.y - fill.bounds.minY) * scale))
            guard px >= 0, py >= 0, px < image.width, py < image.height else { return fail("Raster sample leaves the native fill image") }
            let offset = py * image.bytesPerRow + px * 4
            guard bytes[offset + 3] == 255 else { return fail("The actual fill image contains a transparent or antialiased coverage sample") }
            guard let actual = CaptureRaster.sRGBPixel(bitmap, x: x, y: y),
                  actual == [Double(bytes[offset]), Double(bytes[offset + 1]), Double(bytes[offset + 2]), 255] else {
                return fail("The final raster differs from the exact opaque source pixel")
            }
            count += 1
        } }
        result["pixel_count"] = count; result["pixel_rect"] = ["x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0]
        result["candidate_opaque_cover"] = count > 0
        return result
    }
}
