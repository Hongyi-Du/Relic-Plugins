import Foundation

enum CaptureMeasurements {
    /// JSON has no nonfinite number. Preserve its exact path and native spelling
    /// as an explicit failed measurement, with null in the numeric slot.
    static func jsonValue(_ value: Any, path: String = "$", errors: inout [[String: String]]) -> Any {
        if let number = value as? NSNumber, !number.doubleValue.isFinite {
            errors.append(["path": path, "native_value": number.stringValue, "reason": "Native measurement is not a finite JSON number"])
            return NSNull()
        }
        if let map = value as? [String: Any] {
            var result: [String: Any] = [:]
            for (key, item) in map { result[key] = jsonValue(item, path: path + "." + key, errors: &errors) }
            return result
        }
        if let rows = value as? [Any] { return rows.enumerated().map { jsonValue($0.element, path: path + "[\($0.offset)]", errors: &errors) } }
        return value
    }
}
