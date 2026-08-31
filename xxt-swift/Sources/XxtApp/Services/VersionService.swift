import Foundation

/// 版本信息的单一访问点。
///
/// 版本号的真正『唯一来源』是 `script/build_and_run.sh` 中的 `MARKETING_VERSION`，
/// 它会在组装时写入 `Info.plist` 的 `CFBundleShortVersionString` / `CFBundleVersion`。
/// 本服务只负责在运行时从 `Bundle.main` 读取该值，任何 UI 需要展示版本时都应走这里，
/// 避免在 Swift 侧二次硬编码造成多源漂移。
enum VersionService {
    /// 短版本号，例如 `2.2`。
    static var marketingVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
    }

    /// 构建号，例如 `2.2`。
    static var bundleVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? marketingVersion
    }

    /// 显示名称，例如 `学习通作业爬取工具`。
    static var appName: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "学习通作业爬取工具"
    }

    /// 供设置页展示的一整行，例如 `学习通作业爬取工具 v2.2`。
    static var displayLine: String {
        "\(appName) v\(marketingVersion)"
    }
}