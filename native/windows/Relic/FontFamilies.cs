namespace Relic;

internal static class FontFamilies
{
    // Match app.css's explicit UI fallback order. A single Segoe declaration
    // delegates CJK selection to the platform's unrelated default fallback.
    // This is a production font request, not evidence of the resolved glyph face.
    public const string UI = "Segoe UI Variable Text, Segoe UI, PingFang SC, Microsoft YaHei UI, Noto Sans SC";
}
