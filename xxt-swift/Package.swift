// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "XxtApp",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "XxtApp", targets: ["XxtApp"])
    ],
    targets: [
        .executableTarget(
            name: "XxtApp",
            path: "Sources/XxtApp"
        )
    ]
)