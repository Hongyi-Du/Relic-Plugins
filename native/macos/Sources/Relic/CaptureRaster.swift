import AppKit

/// Configure the empty destination before any view draws into it. AppKit's
/// default cache bitmap can use Generic RGB; blending there and subsequently
/// converting its pixels to sRGB changes translucent colors. The browser PNG
/// and the canonical brush measurements use sRGB, so the native drawing target
/// must use that space too. Never retag an already-rendered image.
@MainActor enum CaptureRaster {
    static func forView(_ view: NSView) -> NSBitmapImageRep? {
        guard let allocation = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return nil }
        return prepare(allocation)
    }
    static func composite(width: Int, height: Int, draw: (NSRect) -> Void) -> NSBitmapImageRep? {
        guard let space = CGColorSpace(name: CGColorSpace.sRGB),
              let destination = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
                space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue) else { return nil }
        // A retagged NSBitmapImageRep can retain an immutable CGImage snapshot.
        // Draw into an actual owned sRGB context, then snapshot only AFTER the
        // native views have been composited. Never encode a pre-draw snapshot.
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: destination, flipped: false)
        draw(NSRect(x: 0, y: 0, width: CGFloat(width), height: CGFloat(height)))
        destination.flush()
        NSGraphicsContext.restoreGraphicsState()
        guard let image = destination.makeImage() else { return nil }
        return NSBitmapImageRep(cgImage: image)
    }
    private static func prepare(_ allocation: NSBitmapImageRep) -> NSBitmapImageRep? {
        guard let bitmap = allocation.retagging(with: .sRGB), let bytes = bitmap.bitmapData else { return nil }
        bytes.update(repeating: 0, count: bitmap.bytesPerRow * bitmap.pixelsHigh)
        return bitmap
    }
    static func evidence(_ bitmap: NSBitmapImageRep) -> [String: Any] {
        ["color_space": bitmap.colorSpace.localizedName as Any? ?? NSNull(),
         "cg_color_space": bitmap.cgImage?.colorSpace?.name as Any? ?? NSNull(),
         "pixel_width": bitmap.pixelsWide, "pixel_height": bitmap.pixelsHigh,
         "bits_per_sample": bitmap.bitsPerSample, "samples_per_pixel": bitmap.samplesPerPixel,
         "bitmap_format": bitmap.bitmapFormat.rawValue, "has_alpha": bitmap.hasAlpha, "is_planar": bitmap.isPlanar,
         "bytes_per_row": bitmap.bytesPerRow,
         "configuration": "Empty compatible bitmap initialized as sRGB before actual native drawing"]
    }
    static func sRGBPixel(_ bitmap: NSBitmapImageRep, x: Int, y: Int) -> [Double]? {
        // colorAt creates a calibrated NSColor even when the underlying bitmap
        // carries sRGB; converting that color a second time changes the bytes
        // (CI: raw 27 becomes 35.9). Read the tagged native pixel samples directly.
        guard bitmap.colorSpace == .sRGB, bitmap.bitsPerSample == 8,
              !bitmap.bitmapFormat.contains(.floatingPointSamples),
              bitmap.samplesPerPixel == (bitmap.hasAlpha ? 4 : 3),
              x >= 0, y >= 0, x < bitmap.pixelsWide, y < bitmap.pixelsHigh else { return nil }
        var samples = [Int](repeating: 0, count: bitmap.samplesPerPixel)
        bitmap.getPixel(&samples, atX: x, y: y)
        let firstAlpha = bitmap.hasAlpha && bitmap.bitmapFormat.contains(.alphaFirst)
        let alpha = bitmap.hasAlpha ? Double(samples[firstAlpha ? 0 : 3]) : 255
        let firstColor = firstAlpha ? 1 : 0
        let premultiplied = bitmap.hasAlpha && !bitmap.bitmapFormat.contains(.alphaNonpremultiplied)
        let channels = samples[firstColor..<(firstColor + 3)].map { sample -> Double in
            premultiplied && alpha > 0 ? Double(sample) * 255 / alpha : Double(sample)
        }
        return channels + [alpha]
    }
}
