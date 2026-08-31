import SwiftUI

/// 简单的 24 位十六进制颜色初始化（`0xRRGGBB`）。
extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}

/// v2.0 界面主题。仅保留「活力靛蓝」单一主题（不再提供切换入口），
/// 统一从 `AppTheme.indigo` 取色，避免多套主题死代码。
/// 每个主题提供：主色（主按钮 / 进度条 / 状态徽标 / 选中态）、
/// 辅助色（强调点缀），以及一条用于进度条渐变填充的渐变。
struct AppTheme: Identifiable, Hashable {
    let id: String
    let name: String
    /// 圆形色标
    let swatch: Color
    let primary: Color
    let accent: Color
    /// 进度条渐变填充
    let gradient: [Color]

    /// 唯一生效主题：活力靛蓝
    static let indigo = AppTheme(id: "indigo", name: "活力靛蓝", swatch: Color(hex: 0x4F46E5),
                                 primary: Color(hex: 0x4F46E5), accent: Color(hex: 0x22D3EE),
                                 gradient: [Color(hex: 0x4F46E5), Color(hex: 0x22D3EE)])

    /// 兼容按 id 查找（历史调用），恒返回靛蓝。
    static func find(_ id: String?) -> AppTheme {
        indigo
    }
}