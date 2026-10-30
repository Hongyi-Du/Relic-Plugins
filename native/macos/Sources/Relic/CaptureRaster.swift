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
    static func canvas(width: Int, height: Int) -> NSBitmapImageRep? {
        guard let allocation = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: width * 4, bitsPerPixel: 32) else { return nil }
        return prepare(allocation)
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
         "bytes_per_row": bitmap.bytesPerRow,
         "configuration": "Empty compatible bitmap initialized as sRGB before actual native drawing"]
    }
}
