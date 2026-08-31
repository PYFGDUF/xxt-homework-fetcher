import SwiftUI

/// 启动时的网络代理提示弹窗：检测到 VPN/系统代理可能影响抓取稳定性时弹出。
/// 风格与扫码登录弹窗一致（主题色 Icon + 液态玻璃圆底 + 品牌/描边按钮）。
struct ProxyWarnView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        VStack(spacing: 16) {
            header
            title
            message
            actionButtons
        }
        .padding(22)
        .frame(width: 392)
        .background(Rectangle().fill(Color(nsColor: .windowBackgroundColor)))
    }

    // MARK: - 头部主题图标（液态玻璃分层）
    private var header: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(colors: [Color.white.opacity(0.9), Color.white.opacity(0.6)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing)
                )
                .frame(width: 72, height: 72)
                .overlay(Circle().strokeBorder(Color.white.opacity(0.6), lineWidth: 1))
                .shadow(color: .black.opacity(0.12), radius: 10, y: 4)
            Image(systemName: "network.badge.shield.half.filled")
                .font(.system(size: 28, weight: .medium))
                .foregroundStyle(app.theme.primary)
        }
    }

    // MARK: - 标题
    private var title: some View {
        Text("检测到网络代理")
            .font(.title2.weight(.semibold))
            .foregroundStyle(app.theme.primary)
    }

    // MARK: - 提示正文
    private var message: some View {
        VStack(spacing: 8) {
            Text("当前系统启用了\(detectedProxy)。网络代理 / VPN 可能影响抓取稳定性和登录状态，建议先关闭代理再使用本工具。")
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.center)
            Text(detail)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .lineSpacing(3)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(app.theme.primary.opacity(0.08)))
        }
    }

    private var detectedProxy: String {
        app.proxyMessage.isEmpty ? "网络代理" : "代理（\(app.proxyMessage)）"
    }

    private var detail: String {
        "你可以在「系统设置 → 网络 → 你的连接 → 详细信息 → 代理」中关闭；\n若使用的是 VPN 客户端，请退出后再开始抓取。"
    }

    // MARK: - 操作按钮
    private var actionButtons: some View {
        HStack(spacing: 10) {
            Button("我知道了") {
                app.showProxyAlert = false
            }
            .brandButtonStyle(theme: app.theme)
            .frame(width: 200)
        }
        .padding(.top, 4)
    }
}