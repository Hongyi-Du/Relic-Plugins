import Foundation

public enum RuleExample {
    // Mirrors exampleText: choose the first meaningful argument, normalize
    // whitespace and apply the reference's UTF-16 display limit.
    public static func text(_ call: Node) -> String {
        let input = call["input"]
        var argument = ["command", "file_path", "path"].map { input[$0].text }.first { !$0.isEmpty } ?? ""
        if argument.isEmpty, !input.object.isEmpty,
           let data = try? JSONSerialization.data(withJSONObject: input.raw, options: [.sortedKeys, .withoutEscapingSlashes]),
           let json = String(data: data, encoding: .utf8) { argument = json }
        return ReferenceText.clip([call["tool"].text, argument].filter { !$0.isEmpty }.joined(separator: " "), to: 160)
    }
}
