import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        huanxinRoot
        // 登录阻断层改为 macOS 原生 sheet（非可关闭，避免 Escape 误关）
        .sheet(isPresented: Bindable(app).isLoggingIn, content: {
            LoginPromptView()
        })
        // 启动时检测到网络代理（VPN 可能影响抓取稳定性）的提示弹窗
        .sheet(isPresented: Bindable(app).showProxyAlert, content: {
            ProxyWarnView()
        })
        // 扫码登录成功提示
        .alert("登录成功", isPresented: Bindable(app).showLoginSuccess) {
            Button("好的", role: .cancel) { }
        } message: {
            Text(app.loginSuccessMessage)
        }
        // 课程 URL 为空时点击刷新的提示
        .alert("无法加载作业", isPresented: Bindable(app).showURLError) {
            Button("好的", role: .cancel) { }
        } message: {
            Text(app.urlErrorMessage)
        }
        // 抓取完成后图片下载失败提醒
        .alert("图片下载失败", isPresented: Bindable(app).showImageFailAlert) {
            Button("好的", role: .cancel) { }
        } message: {
            Text(app.imageFailMessage)
        }
        .onAppear {
            app.applyAppearance()
            app.startEngine()
        }
        // 外观变化时一次性设置窗口外观（替代 .preferredColorScheme 逐渲染 re-apply，规避重绘闪烁）
        .onChange(of: app.preferredColorScheme) {
            app.applyAppearance()
        }
    }

    /// 焕新界面的根：任务流 + 主题菜单 + 通用工具
    private var huanxinRoot: some View {
        HuanxinView()
            .toolbar { huanxinToolbar }
            .tint(app.theme.primary)
    }

    /// 焕新界面的工具栏（独立拆分以避免复杂类型导致的 type-check 超时）
    @ToolbarContentBuilder
    private var huanxinToolbar: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            Button {
                app.openLastOutput()
            } label: {
                Label("输出目录", systemImage: "folder")
            }
            .buttonStyle(.borderless)
            .help("打开输出目录")
        }
        ToolbarItem(placement: .navigation) {
            SettingsLink {
                Label("设置", systemImage: "gearshape")
            }
            .buttonStyle(.borderless)
            .help("设置")
        }
    }
}