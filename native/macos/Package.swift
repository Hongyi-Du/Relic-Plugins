// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Relic",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "Relic", targets: ["Relic"])],
    targets: [
        .target(name: "RelicCore"),
        .executableTarget(name: "Relic", dependencies: ["RelicCore"]),
        .testTarget(name: "RelicCoreTests", dependencies: ["RelicCore"]),
        .testTarget(name: "RelicModelTests", dependencies: ["Relic", "RelicCore"])
    ]
)
