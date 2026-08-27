import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var app

    @State private var detailTab: DetailTab = .log

    enum DetailTab: String, CaseIterable, Identifiable {
        case log = "运行日志"
        case repair = "待修复"
        case history = "历史"

        var id: String { rawValue }
    }

    var body: some View {
        Group {
            switch app.uiMode {
            case .huanxin:
                huanxinRoot
            case .classic:
                classicRoot
            }
        }
        // 登录阻断层改为 macOS 原生 sheet（非可关闭，避免 Escape 误关）
        .sheet(isPresented: Bindable(app).isLoggingIn, content: {
            LoginPromptView()
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

    /// 焕新界面的根：任务流 + 主题菜单 + 界面切换 + 通用工具
    private var huanxinRoot: some View {
        HuanxinView()
            .toolbar { huanxinToolbar }
            .tint(app.theme.primary)
    }

    /// 焕新界面的工具栏（独立拆分以避免复杂类型导致的 type-check 超时）
    @ToolbarContentBuilder
    private var huanxinToolbar: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            uiModeSwitcher
        }
        ToolbarItem(placement: .primaryAction) {
            themeMenu
        }
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

    /// 经典界面的根：原有 NavigationSplitView + 分段详情
    private var classicRoot: some View {
        NavigationSplitView {
            SidebarView()
                .navigationSplitViewColumnWidth(min: 240, ideal: 300, max: 420)
        } detail: {
            detail
        }
        .navigationSplitViewStyle(.balanced)
        .toolbar {
            ToolbarItem(placement: .navigation) {
                uiModeSwitcher
            }
            // 详情分段切换器（日志/待修复/历史）放原生工具栏居中，与新“焕新界面”风格一致
            ToolbarItem(placement: .principal) {
                Picker("", selection: $detailTab) {
                    ForEach(DetailTab.allCases) { tab in
                        Text(tab.rawValue).tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
                .accessibilityLabel("详情视图")
                .help("切换详情视图")
            }
            // 抓取相关的主操作按钮仅在本体（日志/待修复）界面显示；
            // 「历史」界面隐藏停止/加载作业/抓取，只保留自己的刷新，避免出现两个刷新图标。
            if detailTab != .history {
                ToolbarItemGroup(placement: .primaryAction) {
                    // 一键复制运行日志
                    Button {
                        app.copyLogsToClipboard()
                    } label: {
                        Label("复制日志", systemImage: "doc.on.doc")
                    }
                    .help("复制全部运行日志到剪贴板")
                    if app.isRunning {
                        ProgressView()
                            .controlSize(.small)
                            .help("抓取进行中")
                    }
                    Button {
                        app.stopTask()
                    } label: {
                        Label("停止", systemImage: "stop.fill")
                    }
                    .tint(.red)
                    .disabled(!app.isRunning)

                    Button {
                        app.loadHomeworks()
                    } label: {
                        Label("加载作业", systemImage: "arrow.clockwise")
                    }
                    .disabled(app.isEngineBusy)

                    Button {
                        app.startSelected()
                    } label: {
                        Label("抓取选中", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return, modifiers: [.command])
                    .disabled(app.isRunning || app.isEngineBusy || app.selectedHomeworkIDs.isEmpty)
                }
            }
            // 按当前详情标签展示对应操作，统一收进原生工具栏（取代各子页悬浮的工具带）
            ToolbarItemGroup {
                switch detailTab {
                case .log:
                    Toggle(isOn: Bindable(app).logAutoScroll) {
                        Image(systemName: "arrow.down.circle.fill")
                            .symbolRenderingMode(.hierarchical)
                    }
                    .toggleStyle(.button)
                    .help("自动滚动到底部")
                    Button {
                        app.clearLogs()
                    } label: {
                        Label("清空日志", systemImage: "trash")
                    }
                case .repair:
                    Button {
                        app.collectRepairItems()
                        app.repairSelection.removeAll()
                    } label: {
                        Label("扫描", systemImage: "magnifyingglass")
                    }
                    .help("检测答案缺失的作业")
                    Button {
                        app.repairSelected(Array(app.repairSelection))
                    } label: {
                        Label("修复选中", systemImage: "hammer")
                    }
                    .disabled(app.repairSelection.isEmpty || app.isRunning)
                case .history:
                    Button {
                        app.refreshHistory()
                    } label: {
                        Label("刷新", systemImage: "arrow.clockwise")
                    }
                }
            }
            ToolbarItem(placement: .navigation) {
                Button {
                    app.openLastOutput()
                } label: {
                    Label("输出目录", systemImage: "folder")
                }
                .help("打开输出目录")
            }
            ToolbarItem(placement: .navigation) {
                // 系统统一的设置窗口入口（对应 Settings 场景，Cmd+, 同样可用）
                SettingsLink {
                    Label("设置", systemImage: "gearshape")
                }
                .help("设置")
            }
        }
        // 登录阻断层改为 macOS 原生 sheet（非可关闭，避免 Escape 误关）
        .sheet(isPresented: Bindable(app).isLoggingIn, content: {
            LoginPromptView()
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
            app.startEngine()
        }
    }

    private var detail: some View {
        Group {
            switch detailTab {
            case .log: logDetail
            case .repair: RepairListView()
            case .history: HistoryView()
            }
        }
        .navigationTitle("学习通作业抓取")
        .navigationSubtitle(app.isRunning ? "运行中" : app.selectedHomeworkIDs.isEmpty ? "未选择作业" : "已选择 \(app.selectedHomeworkIDs.count) 个作业")
        .safeAreaInset(edge: .bottom) {
            detailFooter
        }
    }

    /// 顶部「焕新 / 经典」界面切换开关（两个模式共用）
    private var uiModeSwitcher: some View {
        Picker("", selection: Bindable(app).uiMode) {
            ForEach(AppUIMode.allCases) { mode in
                Label(mode.rawValue, systemImage: mode == .huanxin ? "sparkle" : "square.grid.2x2")
                    .tag(mode)
            }
        }
        .pickerStyle(.menu)
        .labelsHidden()
        .fixedSize()
        .help("切换界面外观")
    }

    /// 主题色选择菜单（焕新界面专用入口，经典界面保持原 accentColor）
    private var themeMenu: some View {
        Menu {
            ForEach(AppTheme.all) { theme in
                Button {
                    app.themeID = theme.id
                } label: {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(theme.swatch)
                            .frame(width: 14, height: 14)
                        Text(theme.name)
                        if theme.id == app.themeID {
                            Spacer()
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            Label("主题", systemImage: "paintpalette")
        }
        .help("切换主题色")
    }

    private var detailFooter: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Image(systemName: "folder")
                    .foregroundStyle(.secondary)
                    .font(.body)
                Text(app.settings.outputDir.isEmpty ? "未设置输出目录" : app.settings.outputDir)
                    .font(.callout.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer()
                if app.isRunning && app.progressTotal > 0 {
                    Text("\(app.progressPercent)%")
                        .font(.system(.title3, design: .rounded, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
            // 抓取进行中：用醒目的大进度条突出爬取进度
            if app.isRunning && app.progressTotal > 0 {
                HStack(spacing: 10) {
                    ProgressView(value: app.progressFraction)
                        .progressViewStyle(.linear)
                        .tint(.accentColor)
                    Text("\(app.progressCurrent)/\(app.progressTotal)")
                        .font(.callout.monospaced())
                        .foregroundStyle(.secondary)
                        .fixedSize()
                }
                Text(app.courseName.isEmpty ? "正在抓取作业…" : "正在抓取：\(app.courseName)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            } else if app.isRunning {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text("正在准备抓取…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            } else if app.isEngineBusy {
                HStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text("引擎启动中…")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.thinMaterial)
    }

    /// 「运行日志」页：上下各占一半。上方为大字号进度面板（更醒目），
    /// 下方为日志区，从而把日志限制在约一半垂直空间内。
    private var logDetail: some View {
        GeometryReader { geo in
            VStack(spacing: 0) {
                progressPanel
                    .frame(height: max(120, geo.size.height * 0.5))
                Divider()
                LogView()
                    .frame(height: max(120, geo.size.height * 0.5))
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
    }

    /// 醒目的进度面板：大字号百分比 + 大进度条 + n/N 与课程名。
    private var progressPanel: some View {
        VStack(spacing: 12) {
            if app.isRunning && app.progressTotal > 0 {
                Text("\(app.progressPercent)%")
                    .font(.system(size: 60, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(.tint)
                Text(app.courseName.isEmpty ? "正在抓取作业…" : "正在抓取：\(app.courseName)")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                ProgressView(value: app.progressFraction)
                    .progressViewStyle(.linear)
                    .tint(.accentColor)
                    .controlSize(.large)
                Text("已完成 \(app.progressCurrent) / \(app.progressTotal) 个作业")
                    .font(.title3.weight(.semibold))
                    .monospacedDigit()
            } else if app.isRunning {
                VStack(spacing: 10) {
                    ProgressView().controlSize(.large)
                    Text("正在准备抓取…")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
            } else if app.isEngineBusy {
                VStack(spacing: 10) {
                    ProgressView().controlSize(.large)
                    Text("引擎启动中…")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                }
            } else {
                VStack(spacing: 10) {
                    Image(systemName: "checkmark.seal")
                        .font(.system(size: 44))
                        .foregroundStyle(.tertiary)
                    Text("就绪")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                    Text("选择左侧作业后点击「抓取选中」开始")
                        .font(.subheadline)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.thinMaterial)
        .padding(.horizontal, 20)
    }
}