import SwiftUI
import AppKit

struct SettingsView: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var draft: DraftSettings
    @State private var confirmLogout = false
    /// 焕新界面：顶部分段分组（通用/选项/登录）
    @State private var huanxinTab: Int = 0

    private struct DraftSettings {
        var outputDir: String
        var autoExportPDF: Bool
        var forceRegrab: Bool
        var openDirOnComplete: Bool
        var playSoundOnComplete: Bool
        var notifyOnComplete: Bool
        var showSourceURL: Bool
        var appearance: String
    }

    init() {
        // 从环境读取较繁琐，改为在 body onAppear/onChange 同步
        _draft = State(initialValue: DraftSettings(outputDir: "", autoExportPDF: false,
                                                   forceRegrab: false,
                                                   openDirOnComplete: false, playSoundOnComplete: true,
                                                   notifyOnComplete: true, showSourceURL: true,
                                                   appearance: "system"))
    }

    var body: some View {
        Group {
            if app.uiMode == .huanxin {
                huanxinBody
            } else {
                classicBody
            }
        }
        .frame(minWidth: 430, maxWidth: 540, minHeight: 400)
        .alert("确认退出登录？", isPresented: $confirmLogout) {
            Button("取消", role: .cancel) { }
            Button("退出登录", role: .destructive) {
                app.logout()
                dismiss()
            }
        } message: {
            Text("这将清除本地保存的登录状态（state.json 等），再次抓取时需重新扫码登录。")
        }
        .onAppear {
            let s = app.settings
            draft = DraftSettings(outputDir: s.outputDir,
                                  autoExportPDF: s.autoExportPDF,
                                  forceRegrab: s.forceRegrab, openDirOnComplete: s.openDirOnComplete,
                                  playSoundOnComplete: app.playSoundOnComplete,
                                  notifyOnComplete: app.notifyOnComplete,
                                  showSourceURL: s.showSourceURL,
                                  appearance: s.appearance)
        }
    }

    // MARK: - 经典界面：系统标准 TabView + Form(.grouped)

    private var classicBody: some View {
        TabView {
            Form {
                Section("输出") {
                    HStack {
                        TextField("输出目录", text: $draft.outputDir)
                        chooseDirButton
                    }
                }

                Section("外观") {
                    Picker("外观", selection: $draft.appearance) {
                        Text("跟随系统").tag("system")
                        Text("浅色").tag("light")
                        Text("深色").tag("dark")
                    }
                    .pickerStyle(.segmented)
                }
            }
            .formStyle(.grouped)
            .tabItem { Label("通用", systemImage: "gearshape") }

            Form {
                Section("选项") {
                    Toggle("保存后自动导出 PDF", isOn: $draft.autoExportPDF)
                    Toggle("强制重新抓取已完成的作业", isOn: $draft.forceRegrab)
                    Toggle("抓取完成后自动打开输出目录", isOn: $draft.openDirOnComplete)
                    Toggle("抓取完成后播放提示音", isOn: $draft.playSoundOnComplete)
                    Toggle("抓取完成后发送系统通知", isOn: $draft.notifyOnComplete)
                    Toggle("文档中展示来源 URL", isOn: $draft.showSourceURL)
                }

                Section("登录") {
                    loginRow
                }
            }
            .formStyle(.grouped)
            .tabItem { Label("选项", systemImage: "slider.horizontal.3") }
        }
        // 底部操作带：取消/保存，沿用系统 grouped 表单的工具栏区域形态
        .safeAreaInset(edge: .bottom) {
            bottomBar
        }
    }

    // MARK: - 焕新界面：扁平卡片 + 顶部分段 + 主题色操作（与主界面一致）

    private var huanxinBody: some View {
        VStack(spacing: 0) {
            huanxinTabBar

            ScrollView {
                VStack(spacing: 14) {
                    switch huanxinTab {
                    case 0:
                        generalCard.transition(.asymmetric(
                            insertion: .opacity.combined(with: .move(edge: .bottom)),
                            removal: .opacity.combined(with: .move(edge: .top))))
                    case 1:
                        optionsCard.transition(.asymmetric(
                            insertion: .opacity.combined(with: .move(edge: .bottom)),
                            removal: .opacity.combined(with: .move(edge: .top))))
                    default:
                        loginCard.transition(.asymmetric(
                            insertion: .opacity.combined(with: .move(edge: .bottom)),
                            removal: .opacity.combined(with: .move(edge: .top))))
                    }
                }
                .animation(.easeInOut(duration: 0.28), value: huanxinTab)
                .padding(20)
            }

            Divider()
            bottomBar
        }
        .tint(app.theme.primary)
    }

    /// 焕新界面顶部分段栏：复用主题色胶囊分段组件
    private var huanxinTabBar: some View {
        ThemeCapsuleTabs(
            theme: app.theme,
            options: [
                (label: "通用", icon: "gearshape", value: 0),
                (label: "选项", icon: "slider.horizontal.3", value: 1),
                (label: "登录", icon: "person.badge.key", value: 2)
            ],
            selection: $huanxinTab
        )
        .padding(.horizontal, 24)
        .padding(.top, 18)
    }

    /// 通用：输出目录（图标化信息头 + 前导图标字段）
    private var generalCard: some View {
        settingSection(icon: "folder", title: "输出目录", subtitle: "抓取文件的保存位置") {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("输出目录")
                        .font(.callout.weight(.medium))
                        .foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        Image(systemName: "folder")
                            .font(.body)
                            .foregroundStyle(.tertiary)
                        TextField("未设置输出目录", text: $draft.outputDir)
                            .textFieldStyle(.plain)
                        Spacer(minLength: 4)
                        chooseDirButton
                    }
                    .padding(.horizontal, 11)
                    .padding(.vertical, 8)
                    .background(fieldBackground)
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("外观")
                        .font(.callout.weight(.medium))
                        .foregroundStyle(.secondary)
                    ThemeCapsuleTabs(
                        theme: app.theme,
                        options: [
                            (label: "跟随系统", icon: "circle.lefthalf.filled", value: "system"),
                            (label: "浅色", icon: "sun.max", value: "light"),
                            (label: "深色", icon: "moon.fill", value: "dark")
                        ],
                        selection: $draft.appearance
                    )
                }
                .padding(.top, 4)
            }
        }
    }

    /// 选项：图标徽标开关行（外观已移至「通用」）
    private var optionsCard: some View {
        settingSection(icon: "slider.horizontal.3", title: "抓取选项", subtitle: "作业保存与完成的反馈方式") {
            VStack(spacing: 0) {
                settingToggle("doc.zipper", title: "导出 PDF", subtitle: "保存 Word 后自动转换", isOn: $draft.autoExportPDF)
                rowDivider
                settingToggle("arrow.clockwise", title: "重新抓取已完成作业", isOn: $draft.forceRegrab)
                rowDivider
                settingToggle("folder", title: "完成后打开输出目录", isOn: $draft.openDirOnComplete)
                rowDivider
                settingToggle("link", title: "展示来源 URL", subtitle: "在文档标题下方显示：来源：链接", isOn: $draft.showSourceURL)
                rowDivider
                settingToggle("speaker.wave.2", title: "完成播放提示音", isOn: $draft.playSoundOnComplete)
                rowDivider
                settingToggle("bell", title: "完成发送系统通知", isOn: $draft.notifyOnComplete)
            }
        }
    }

    /// 登录 / 退出
    private var loginCard: some View {
        settingSection(icon: "person.badge.key", title: "登录状态", subtitle: app.isLoggedIn ? "已登录，可直接抓取作业" : "尚未登录学习通") {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: app.isLoggedIn ? "checkmark.circle.fill" : "exclamationmark.circle")
                        .foregroundStyle(app.isLoggedIn ? Color(nsColor: .systemGreen) : Color(nsColor: .systemOrange))
                    Text(app.isLoggedIn
                         ? "登录态有效，抓取将自动使用已保存的登录信息。"
                         : "登录后可开始抓取作业，登录状态会自动保存在本地。")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
                .padding(.top, 2)
                loginRow
            }
        }
    }

    private var loginRow: some View {
        Group {
            if app.isLoggedIn {
                Button(role: .destructive) {
                    confirmLogout = true
                } label: {
                    Label("退出登录", systemImage: "rectangle.portrait.and.arrow.right")
                }
                .help("清除本地登录状态（含 state.json、cookies.txt），下次需重新登录")
            } else {
                Button {
                    // 发起登录并立即关闭设置窗口：扫码登录 sheet 统一由主窗口承载
                    app.startLogin()
                    dismiss()
                } label: {
                    Label("登录学习通", systemImage: "qrcode")
                }
                .help("发起扫码登录学习通，登录成功后可开始抓取作业")
            }
        }
        .brandButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
    }

    // MARK: - 复用 UI 片段

    private var fieldBackground: some View {
        RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(Color(nsColor: .textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(Color(nsColor: .separatorColor).opacity(0.8), lineWidth: 1)
            )
    }

    /// 行间分隔（左右与内容对齐，避免贴着卡片边缘）
    private var rowDivider: some View {
        Divider()
            .padding(.vertical, 12)
    }

    /// 图标化卡片头 + 内容的设置分区卡（焕新风格统一外壳）
    private func settingSection<Content: View>(
        icon: String,
        title: String,
        subtitle: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 11) {
                IconBadge(symbol: icon, tint: app.theme.primary, soft: app.theme.primary.opacity(0.12))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.body.weight(.semibold))
                    Text(subtitle)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            .padding(.bottom, 18)

            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color(nsColor: .separatorColor).opacity(0.4), lineWidth: 1)
        )
    }

    /// 图标徽标开关行：左侧主题色软底图标 + 标题/副标题，右侧系统 Switch
    private func settingToggle(
        _ icon: String,
        title: String,
        subtitle: String? = nil,
        isOn: Binding<Bool>
    ) -> some View {
        Toggle(isOn: isOn) {
            HStack(spacing: 12) {
                IconBadge(symbol: icon, tint: app.theme.primary, soft: app.theme.primary.opacity(0.10))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.body.weight(.medium))
                    if let subtitle {
                        Text(subtitle)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 8)
            }
        }
        .toggleStyle(.switch)
        .tint(app.theme.primary)
    }

    private var chooseDirButton: some View {
        Button {
            let panel = NSOpenPanel()
            panel.canChooseDirectories = true
            panel.canChooseFiles = false
            panel.allowsMultipleSelection = false
            if panel.runModal() == .OK, let url = panel.url {
                draft.outputDir = url.path
            }
        } label: {
            Text("选择…")
        }
        .outlineButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
    }

    private var bottomBar: some View {
        HStack {
            Spacer()
            Button("取消") { dismiss() }
                .outlineButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
            Button("保存") {
                writeBack()
                app.saveSettings()
                dismiss()
            }
            .brandButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
            .keyboardShortcut(.defaultAction)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(app.uiMode == .huanxin ? AnyShapeStyle(Color(nsColor: .windowBackgroundColor)) : AnyShapeStyle(.bar))
    }

    // MARK: - 保存

    private func writeBack() {
        var s = app.settings
        s.outputDir = draft.outputDir
        s.autoExportPDF = draft.autoExportPDF
        s.forceRegrab = draft.forceRegrab
        s.openDirOnComplete = draft.openDirOnComplete
        s.showSourceURL = draft.showSourceURL
        s.appearance = draft.appearance
        app.settings = s
        app.setPlaySound(draft.playSoundOnComplete)
        app.setNotify(draft.notifyOnComplete)
    }
}

/// 图标徽标：主题色软底圆角方块 + 主题色图标，用于卡片头与开关行
private struct IconBadge: View {
    let symbol: String
    let tint: Color
    let soft: Color

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(soft)
                .frame(width: 30, height: 30)
            Image(systemName: symbol)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(tint)
        }
    }
}

/// 主题色胶囊分段栏：激活项主题色填充 + 白字，切换时胶囊弹簧滑动。
/// 用于设置界面顶部分段栏、外观切换等，图标 + 文案可选。
private struct ThemeCapsuleTabs<Tag: Hashable>: View {
    let theme: AppTheme
    var options: [(label: String, icon: String?, value: Tag)]
    @Binding var selection: Tag
    /// 激活胶囊的几何动画命名空间（按实例隔离，互不影响）
    @Namespace private var ns

    var body: some View {
        HStack(spacing: 4) {
            ForEach(Array(options.enumerated()), id: \.element.value) { _, opt in
                Button {
                    withAnimation(.spring(response: 0.35, dampingFraction: 0.8)) {
                        selection = opt.value
                    }
                } label: {
                    HStack(spacing: 5) {
                        if let icon = opt.icon {
                            Image(systemName: icon)
                                .font(.system(size: 11, weight: .semibold))
                        }
                        Text(opt.label)
                            .font(.callout.weight(selection == opt.value ? .semibold : .medium))
                    }
                    .foregroundStyle(selection == opt.value ? Color.white : Color.secondary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .frame(maxWidth: .infinity)
                    .contentShape(Capsule())
                    .background {
                        if selection == opt.value {
                            Capsule()
                                .fill(theme.primary)
                                .shadow(color: theme.primary.opacity(0.35), radius: 5, y: 2)
                                .matchedGeometryEffect(id: "tabPill", in: ns)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
        .background(
            Capsule()
                .fill(Color(nsColor: .controlBackgroundColor).opacity(0.75))
                .overlay(
                    Capsule().strokeBorder(Color(nsColor: .separatorColor).opacity(0.45), lineWidth: 1)
                )
        )
    }
}