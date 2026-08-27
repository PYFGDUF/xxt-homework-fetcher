import SwiftUI
import AppKit

/// 扫码登录弹窗：无头浏览器渲染登录页，抓取二维码 base64 回传显示。
/// 由 ContentView 的 .sheet(isPresented: isLoggingIn) 承载，登录成功/取消后自动关闭。
struct LoginPromptView: View {
    @Environment(AppState.self) private var app
    private let qrSlot: CGFloat = 230
    /// 钥匙图标的呼吸缩放进度
    @State private var keyBreath = false

    var body: some View {
        VStack(spacing: 16) {
            header

            qrArea

            // 提示文字：支持自动换行（lineSpacing + fixedSize）
            Text(tip)
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineSpacing(4)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, alignment: .center)

            actionButtons
        }
        .padding(20)
        .frame(width: 360)
        .background(Rectangle().fill(Color(nsColor: .windowBackgroundColor)))
    }

    // MARK: - 头部钥匙图标（液态玻璃分层，常驻元素）
    private var header: some View {
        ZStack {
            Circle()
                .fill(
                    LinearGradient(colors: [Color.white.opacity(0.9), Color.white.opacity(0.6)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing)
                )
                .frame(width: 78, height: 78)
                .overlay(Circle().strokeBorder(Color.white.opacity(0.6), lineWidth: 1))
                .shadow(color: .black.opacity(0.12), radius: 10, y: 4)
            Image(systemName: "person.badge.key.fill")
                .font(.system(size: 30, weight: .medium))
                .foregroundStyle(app.theme.primary)
                .scaleEffect(keyBreath ? 1.08 : 1)
                .shadow(color: app.theme.primary.opacity(keyBreath ? 0.4 : 0), radius: keyBreath ? 8 : 0)
                .onAppear {
                    withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
                        keyBreath = true
                    }
                }
        }
    }

    // MARK: - 固定 230×230 二维码区域
    @ViewBuilder
    private var qrArea: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.white)
                .frame(width: qrSlot, height: qrSlot)
                .overlay(
                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                        .strokeBorder(Color(nsColor: .separatorColor).opacity(0.5), lineWidth: 1)
                )

            if app.isVerifyingLogin {
                ProgressView("正在验证登录…")
                    .frame(width: qrSlot, height: qrSlot)
            } else if let image = qrImage, !app.loginQRImageB64.isEmpty {
                Image(nsImage: image)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
                    .frame(width: qrSlot - 12, height: qrSlot - 12)
            } else {
                VStack(spacing: 10) {
                    ProgressView()
                        .controlSize(.large)
                    Text("正在获取登录二维码…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var qrImage: NSImage? {
        guard let data = Data(base64Encoded: app.loginQRImageB64) else { return nil }
        return NSImage(data: data)
    }

    // MARK: - 提示文案
    private var tip: String {
        if app.isVerifyingLogin {
            return "正在验证登录状态，请稍候…"
        }
        return "请用「学习通」App 扫描二维码完成登录。\n登录成功后本窗口会自动关闭。"
    }

    // MARK: - 操作按钮
    private var actionButtons: some View {
        HStack(spacing: 10) {
            Button("取消登录") {
                app.cancelLogin()
            }
            .outlineButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)

            Button("已完成登录") {
                app.loginDone()
            }
            .brandButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
            .disabled(app.isVerifyingLogin)
        }
        .padding(.top, 4)
    }
}