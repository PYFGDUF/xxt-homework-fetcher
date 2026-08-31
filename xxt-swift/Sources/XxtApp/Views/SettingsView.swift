import SwiftUI
import AppKit

struct SettingsView: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var draft: DraftSettings
    @State private var confirmLogout = false
    /// 存储空间统计（输出目录占用，按类型分类）
    @State private var storage: AppState.StorageUsage = AppState.StorageUsage()
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
        var concurrencyEnabled: Bool
        var concurrencyWorkers: Int
    }

    init() {
        // 从环境读取较繁琐，改为在 body onAppear/onChange 同步
        _draft = State(initialValue: DraftSettings(outputDir: "", autoExportPDF: false,
                                                   forceRegrab: false,
                                                   openDirOnComplete: false, playSoundOnComplete: true,
                                                   notifyOnComplete: true, showSourceURL: true,
                                                   appearance: "system",
                                                   concurrencyEnabled: false, concurrencyWorkers: 2))
    }

    var body: some View {
        huanxinBody
        .frame(minWidth: 430, maxWidth: 540, minHeight: 400)
        // 每次打开设置窗口都居中显示：macOS 默认会记住窗口上次位置，
        // 通过取到所属 NSWindow 并 center() 强制回到屏幕中央。
        .background(WindowCenterer { window in
            if let window { window.center() }
        })
        .sheet(isPresented: $confirmLogout) {
            ConfirmLogoutView(isPresented: $confirmLogout)
        }
        .onAppear {
            let s = app.settings
            draft = DraftSettings(outputDir: s.outputDir,
                                  autoExportPDF: s.autoExportPDF,
                                  forceRegrab: s.forceRegrab, openDirOnComplete: s.openDirOnComplete,
                                  playSoundOnComplete: app.playSoundOnComplete,
                                  notifyOnComplete: app.notifyOnComplete,
                                  showSourceURL: s.showSourceURL,
                                  appearance: s.appearance,
                                  concurrencyEnabled: s.concurrencyEnabled,
                                  concurrencyWorkers: s.concurrencyWorkers)
            storage = app.storageUsage()
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
                        generalTab.transition(.asymmetric(
                            insertion: .opacity.combined(with: .move(edge: .bottom)),
                            removal: .opacity.combined(with: .move(edge: .top))))
                    case 1:
                        optionsCard.transition(.asymmetric(
                            insertion: .opacity.combined(with: .move(edge: .bottom)),
                            removal: .opacity.combined(with: .move(edge: .top))))
                    case 2:
                        labCard.transition(.asymmetric(
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
                (label: "实验室", icon: "flask", value: 2),
                (label: "登录", icon: "person.badge.key", value: 3)
            ],
            selection: $huanxinTab
        )
        .padding(.horizontal, 24)
        .padding(.top, 18)
    }

    /// 通用页：输出目录卡片 + 存储空间卡片 + 版本卡片
    private var generalTab: some View {
        VStack(spacing: 14) {
            generalCard
            storageCard
            aboutCard
        }
    }

    /// 通用：版本信息（版本号来自 VersionService，单一来源）
    private var aboutCard: some View {
        settingSection(icon: "info.circle", title: "关于", subtitle: "版本信息") {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(VersionService.appName)
                        .font(.body.weight(.semibold))
                    Text("版本 \(VersionService.marketingVersion) (build \(VersionService.bundleVersion))")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
        }
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

    /// 存储空间：统计输出目录占用并按类型分类展示，支持一键清理（NSAlert 二次确认）。
    /// 标题独立居中、字号放大，不与带副标题的卡片共用图标头布局。
    private var storageCard: some View {
        VStack(spacing: 0) {
            Text("存储空间")
                .font(.title3.weight(.bold))
                .frame(maxWidth: .infinity)
                .padding(.bottom, 16)

            VStack(alignment: .leading, spacing: 14) {
                // 总占用
                HStack {
                    Text("总占用")
                        .font(.body.weight(.medium))
                    Spacer(minLength: 8)
                    Text(app.formatBytes(storage.totalBytes))
                        .font(.title2.weight(.bold))
                        .foregroundStyle(storage.isEmpty ? Color.secondary : app.theme.primary)
                }

                // 按类型分类占用
                HStack(spacing: 0) {
                    storageTypeRow(icon: "doc.text", label: "Word", bytes: storage.wordBytes)
                    rowDivider.padding(.horizontal, 10)
                    storageTypeRow(icon: "photo", label: "图片", bytes: storage.imageBytes)
                    rowDivider.padding(.horizontal, 10)
                    storageTypeRow(icon: "doc.richtext", label: "PDF", bytes: storage.pdfBytes)
                    rowDivider.padding(.horizontal, 10)
                    storageTypeRow(icon: "archivebox", label: "其他", bytes: storage.otherBytes)
                }
                .padding(.vertical, 2)

                Text(storage.runCount > 0
                     ? "共 \(storage.runCount) 个课程输出目录，清理后不可恢复。"
                     : "输出目录为空，无需清理。")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Button {
                    confirmCleanup()
                } label: {
                    Label("一键清理", systemImage: "trash")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.minimalGhostRed)
                .disabled(storage.isEmpty)
                .opacity(storage.isEmpty ? 0.45 : 1)
                .animation(.easeOut(duration: 0.15), value: storage.isEmpty)
                .help("删除输出目录下所有已生成的课程输出与 debug 文件夹，释放磁盘空间")
            }
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color(nsColor: .separatorColor).opacity(0.4), lineWidth: 1)
        )
        .onAppear { storage = app.storageUsage() }
    }

    /// 类型占用行：图标 + 类型名 + 占用大小
    private func storageTypeRow(icon: String, label: String, bytes: Int64) -> some View {
        VStack(spacing: 4) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.subheadline)
                    .foregroundStyle(app.theme.primary)
                Text(label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(app.formatBytes(bytes))
                .font(.callout.weight(.semibold))
                .foregroundStyle(bytes > 0 ? Color.primary : Color.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    /// 一键清理的二次确认（NSAlert，避免同一视图链多个 SwiftUI alert 冲突导致失效）
    private func confirmCleanup() {
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = "确认清理存储空间？"
        alert.informativeText = storage.runCount > 0
            ? "将永久删除输出目录下的 \(storage.runCount) 个课程输出目录及 debug 文件夹（共 \(app.formatBytes(storage.totalBytes))），删除后不可恢复。是否继续？"
            : "输出目录为空，没有可清理的内容。"
        alert.addButton(withTitle: "清理")
        alert.addButton(withTitle: "取消")
        if let window = NSApp.keyWindow {
            alert.beginSheetModal(for: window) { response in
                guard response == .alertFirstButtonReturn else { return }
                app.cleanupOutputFolders()
                storage = app.storageUsage()
            }
        } else {
            let response = alert.runModal()
            guard response == .alertFirstButtonReturn else { return }
            app.cleanupOutputFolders()
            storage = app.storageUsage()
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

    /// 实验室：实验性功能（多线程并发抓取）
    private var labCard: some View {
        settingSection(icon: "flask", title: "实验室", subtitle: "实验性功能，可能影响稳定性") {
            labContent
        }
    }

    /// 实验室内容：多线程并发开关 + 并发线程数选择（开启后显示，最多 4）
    private var labContent: some View {
        VStack(spacing: 0) {
            settingToggle("bolt.horizontal",
                          title: "多线程并发",
                          subtitle: "开启后并行抓取多个作业，提高整体速度（默认关闭）",
                          isOn: $draft.concurrencyEnabled)
            if draft.concurrencyEnabled {
                rowDivider
                HStack(spacing: 12) {
                    IconBadge(symbol: "square.stack.3d.up", tint: app.theme.primary,
                              soft: app.theme.primary.opacity(0.10))
                    VStack(alignment: .leading, spacing: 2) {
                        Text("并发线程数")
                            .font(.body.weight(.medium))
                        Text("最多 4 个并发浏览器")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 8)
                    ThemeCapsuleTabs(
                        theme: app.theme,
                        options: [
                            (label: "2", icon: nil, value: 2),
                            (label: "3", icon: nil, value: 3),
                            (label: "4", icon: nil, value: 4)
                        ],
                        selection: $draft.concurrencyWorkers
                    )
                    .frame(width: 152)
                }
                .padding(.vertical, 4)
            }
        }
        .animation(.easeInOut(duration: 0.18), value: draft.concurrencyEnabled)
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
        .brandButtonStyle(theme: app.theme)
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
            // 卡片头即标题：去掉与下方设置开关行同款的大号图标徽标块，避免「行式」观感。
            // 改用小号主题色图标 + .title2 粗体标题，从排布和字号双层面上与 .body 级设置项拉开层级。
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(app.theme.primary)
                    .frame(width: 20)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.title2.weight(.bold))
                    Text(subtitle)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            .padding(.bottom, 16)

            Divider()
                .padding(.bottom, 14)

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
        .outlineButtonStyle(theme: app.theme)
    }

    private var bottomBar: some View {
        HStack {
            Spacer()
            Button("取消") { dismiss() }
                .outlineButtonStyle(theme: app.theme)
            Button("保存") {
                writeBack()
                app.saveSettings()
                dismiss()
            }
            .brandButtonStyle(theme: app.theme)
            .keyboardShortcut(.defaultAction)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color(nsColor: .windowBackgroundColor))
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
        s.concurrencyEnabled = draft.concurrencyEnabled
        s.concurrencyWorkers = draft.concurrencyWorkers
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

/// 取用宿主窗口的 NSViewRepresentable：视图加入窗口层级后回传其 NSWindow，
/// 用来在每次打开设置窗口时强制将其居中（回调在主线程执行）。
private struct WindowCenterer: NSViewRepresentable {
    var onWindow: (NSWindow?) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            self.onWindow(view.window)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        // 视图重新布局时再次取用窗口（此时 window 非 nil），确保居中生效
        DispatchQueue.main.async {
            self.onWindow(nsView.window)
        }
    }
}