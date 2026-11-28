import Foundation

/// One environment variable, read with getenv. ProcessInfo's environment
/// property builds a dictionary of the whole environment on every read, and
/// the CI capture switches are read in row, Markdown and surface bodies on
/// every update. getenv still sees a variable a test sets while it runs.
enum ProcessEnvironment {
    static func value(_ name: String) -> String? { getenv(name).map { String(cString: $0) } }
    static func contains(_ name: String) -> Bool { getenv(name) != nil }
}
