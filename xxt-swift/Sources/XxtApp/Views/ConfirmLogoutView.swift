import SwiftUI

/// 退出登录确认弹窗：主题样式，与扫码登录 / 代理提示弹窗风格统一。
struct ConfirmLogoutView: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @Binding var isPresented: Bool

    var body: some View {
        VStack(spacing: 16) {
            header
            title
            message
            actionButtons
        }
        .padding(22)
        .frame(width: 380)
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
            Image(systemName: "rectangle.portrait.and.arrow.right")
                .font(.system(size: 28, weight: .medium))
                .foregroundStyle(app.theme.primary)
        }
    }

    // MARK: - 标题
    private var title: some View {
        Text("确认退出登录？")
            .font(.title2.weight(.semibold))
            .foregroundStyle(app.theme.primary)
    }

    // MARK: - 提示正文
    private var message: some View {
        Text("这将清除本地保存的登录状态（state.json 等），\n再次抓取时需重新扫码登录。")
            .font(.callout)
            .foregroundStyle(.secondary)
            .lineSpacing(4)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.center)
    }

    // MARK: - 操作按钮
    private var actionButtons: some View {
        HStack(spacing: 10) {
            Button("取消") {
                isPresented = false
            }
            .outlineButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)

            Button("退出登录") {
                isPresented = false
                app.logout()
                dismiss()
            }
            .brandButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
        }
        .padding(.top, 4)
    }
}