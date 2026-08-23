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

/// v2.0 构建设计的预设主题。
/// 每个主题提供：主色（主按钮 / 进度条 / 状态徽标 / 选中态）、
/// 辅助色（强调点缀），以及一条用于进度条渐变填充分 的渐变。
struct AppTheme: Identifiable, Hashable {
    let id: String
    let name: String
    /// 主题切换菜单里展示的圆形色标
    let swatch: Color
    let primary: Color
    let accent: Color
    /// 进度条渐变填充
    let gradient: [Color]

    static let all: [AppTheme] = [
        AppTheme(id: "indigo", name: "活力靛蓝", swatch: Color(hex: 0x4F46E5),
                 primary: Color(hex: 0x4F46E5), accent: Color(hex: 0x22D3EE),
                 gradient: [Color(hex: 0x4F46E5), Color(hex: 0x22D3EE)]),
        AppTheme(id: "sunset", name: "落日橘", swatch: Color(hex: 0xF97316),
                 primary: Color(hex: 0xF97316), accent: Color(hex: 0xFACC15),
                 gradient: [Color(hex: 0xFB923C), Color(hex: 0xEF4444)]),
        AppTheme(id: "violet", name: "电光紫", swatch: Color(hex: 0x8B5CF6),
                 primary: Color(hex: 0x8B5CF6), accent: Color(hex: 0xEC4899),
                 gradient: [Color(hex: 0x8B5CF6), Color(hex: 0xEC4899)]),
        AppTheme(id: "green", name: "电劲绿", swatch: Color(hex: 0x059669),
                 primary: Color(hex: 0x059669), accent: Color(hex: 0x84CC16),
                 gradient: [Color(hex: 0x10B981), Color(hex: 0x84CC16)]),
        AppTheme(id: "aurora", name: "极光青", swatch: Color(hex: 0x6366F1),
                 primary: Color(hex: 0x6366F1), accent: Color(hex: 0x06B6D4),
                 gradient: [Color(hex: 0x6366F1), Color(hex: 0x06B6D4)]),
    ]

    /// 按 id 查主题，缺省回落到第一个（靛蓝）。
    static func find(_ id: String?) -> AppTheme {
        all.first { $0.id == id } ?? all[0]
    }
}