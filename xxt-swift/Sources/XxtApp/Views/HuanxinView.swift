import SwiftUI

/// v2.0「焕新界面」：简洁大方的高级审美（v2 定稿）
/// 扁平系统底色 + 发丝分隔线 + 充足留白；主题色仅用于主 CTA / 选中态 / 进度填充 / 状态强调。
/// 单页任务流：顶部课程 URL → 中间作业列表 → 底部任务条；结果态覆盖主区为结果卡片。
/// 日志降级为右下角「运行详情」浮动面板，默认收起。
struct HuanxinView: View {
    @Environment(AppState.self) private var app
    @State private var showDetails = false
    @State private var searchText = ""

    private var filteredHomeworks: [HomeworkItem] {
        let list = app.homeworks
        guard !searchText.isEmpty else { return list }
        return list.filter { $0.title.localizedCaseInsensitiveContains(searchText) }
    }
    private var isAllSelected: Bool {
        !app.homeworks.isEmpty &&
        filteredHomeworks.allSatisfy { app.selectedHomeworkIDs.contains($0.id) }
    }

    private var finished: Bool { app.lastRunFinished && !app.isRunning }
    private var running: Bool { app.isRunning }
    private var loading: Bool { !app.isRunning && app.isEngineBusy }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()

            ZStack {
                mainArea
                if finished {
                    resultCard
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.smooth(duration: 0.45), value: finished)
            .animation(.smooth(duration: 0.35), value: loading)

            Divider()
            taskBar
        }
        .tint(app.theme.primary)
        .animation(.easeInOut(duration: 0.3), value: app.themeID)
    }

    // MARK: - 顶部：品牌 + 状态（无装饰，留白克制）

    private var header: some View {
        HStack {
            Text("学习通作业爬取工具")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.primary)
            Spacer()
            HStack(spacing: 6) {
                Circle()
                    .fill(running ? app.theme.primary : (app.isEngineBusy ? .orange : Color.green))
                    .frame(width: 7, height: 7)
                Text(statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 14)
        .padding(.bottom, 10)
    }

    private var statusText: String {
        if running { return "抓取中" }
        if loading { return "加载中" }
        if finished { return "已完成" }
        return "就绪"
    }

    // MARK: - 中间主区域

    private var mainArea: some View {
        VStack(spacing: 0) {
            courseRow
            listHeader
            listBody
        }
    }

    /// ① 课程：纯白字段 + 主题色加载按钮（平坦、无包裹卡）
    private var courseRow: some View {
        HStack(spacing: 10) {
            Text("① 课程")
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
            TextField("粘贴课程 URL", text: Bindable(app).settings.courseURL)
                .textFieldStyle(.plain)
                .font(.body)
                .submitLabel(.go)
                .onSubmit { app.loadHomeworks() }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Color(nsColor: .textBackgroundColor))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1)
                        )
                )
            Button {
                app.loadHomeworks()
            } label: {
                Text("加载")
                    .font(.callout.weight(.semibold))
                    .padding(.horizontal, 6)
            }
            .buttonStyle(.minimalBrand(theme: app.theme))
            .disabled(app.isEngineBusy)
            .help("加载作业列表")
        }
        .padding(.horizontal, 20)
        .padding(.top, 14)
    }

    private var listHeader: some View {
        HStack {
            Text("② 选择作业")
                .font(.caption.weight(.medium))
                .foregroundStyle(.secondary)
            Spacer()
            if !app.homeworks.isEmpty {
                Text("已选 \(app.selectedHomeworkIDs.count) / \(filteredHomeworks.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
                Button("全选") {
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                        app.selectedHomeworkIDs.formUnion(filteredHomeworks.map(\.id))
                    }
                }
                .buttonStyle(.plain)
                .font(.caption)
                .tint(app.theme.primary)
                .hoverLift(shadowColor: .secondary)
                .disabled(isAllSelected)
                Button("清空") {
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                        app.selectedHomeworkIDs.removeAll()
                    }
                }
                .buttonStyle(.plain)
                .font(.caption)
                .tint(app.theme.primary)
                .hoverLift(shadowColor: .secondary)
                .disabled(app.selectedHomeworkIDs.isEmpty)
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 16)
        .padding(.bottom, 6)
    }

    @ViewBuilder
    private var listBody: some View {
        if app.homeworks.isEmpty && loading {
            loadPanel
        } else if app.homeworks.isEmpty {
            idlePanel
        } else if filteredHomeworks.isEmpty {
            VStack {
                ContentUnavailableView.search(text: searchText)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(spacing: 9) {
                    ForEach(filteredHomeworks) { hw in
                        HomeworkRow(item: hw)
                            .transition(.asymmetric(
                                insertion: .opacity.combined(with: .scale(scale: 0.92)).combined(with: .move(edge: .bottom)),
                                removal: .opacity))
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                // 翻页即时流入：每来一页新作业，新增行以弹簧动效弹入
                .animation(.spring(response: 0.5, dampingFraction: 0.75), value: filteredHomeworks.map(\.id))
            }
            .overlay(alignment: .top) {
                // 列表已出现但仍在翻页时，顶部保留细流光条提示“加载中”
                if loading {
                    LoadingTopStrip(theme: app.theme)
                        .padding(.horizontal, 20)
                        .padding(.top, 6)
                        .transition(.opacity)
                }
            }
        }
    }

    /// 加载中：骨架屏占位卡（现代年轻化，替代传统转圈）
    private var loadPanel: some View {
        VStack(spacing: 0) {
            LoadingTopStrip(theme: app.theme)
                .padding(.horizontal, 20)
                .padding(.top, 6)
                .padding(.bottom, 2)
            if !app.courseName.isEmpty {
                HStack {
                    Text(app.courseName)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 10)
            }
            SkeletonCardList()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    /// 空闲：URL 引导
    private var idlePanel: some View {
        VStack(spacing: 12) {
            Image(systemName: "square.stack.3d.up")
                .font(.system(size: 40))
                .foregroundStyle(.tertiary)
            Text("暂无作业")
                .font(.title3.weight(.semibold))
            Text("在上方粘贴课程 URL 后点击「加载」")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 40)
    }

    /// 抓取完成：结果卡（覆盖主区，底部滑入）
    private var resultCard: some View {
        VStack(spacing: 20) {
            Image(systemName: app.runFailCount > 0 ? "exclamationmark.triangle.fill" : "checkmark.seal.fill")
                .font(.system(size: 46))
                .foregroundStyle(app.runFailCount > 0 ? Color(nsColor: .systemOrange) : app.theme.primary)
                .bounceOnCompletion(true)
            Text(app.runFailCount > 0 ? "已完成，含失败项" : "抓取完成")
                .font(.title2.weight(.semibold))
                .foregroundStyle(.primary)
            HStack(spacing: 32) {
                resultStat("成功", value: app.runOkCount, color: Color(nsColor: .systemGreen), icon: "checkmark.circle.fill")
                resultStat("失败", value: app.runFailCount, color: Color(nsColor: .systemRed), icon: "xmark.circle.fill")
                if app.runImageFailCount > 0 {
                    resultStat("图片失败", value: app.runImageFailCount, color: Color(nsColor: .systemOrange), icon: "photo.badge.exclamationmark")
                }
            }
            if !app.lastOutputDir.isEmpty {
                Button {
                    app.openLastOutput()
                } label: {
                    Label("打开输出目录", systemImage: "folder")
                        .font(.callout.weight(.semibold))
                        .padding(.horizontal, 8)
                }
                .buttonStyle(.minimalBrand(theme: app.theme))
            }

            // 结果卡操作：继续抓取 / 返回主菜单
            HStack(spacing: 12) {
                Button {
                    withAnimation(.smooth(duration: 0.45)) { app.backToSelection() }
                } label: {
                    Label("继续抓取", systemImage: "arrow.uturn.backward")
                        .font(.callout.weight(.semibold))
                        .padding(.horizontal, 8)
                }
                .buttonStyle(.minimalGhost)
                .help("回到作业选择页面，重新选择后再次抓取")

                Button {
                    withAnimation(.smooth(duration: 0.45)) { app.backToMainMenu() }
                } label: {
                    Label("抓取其他课程作业", systemImage: "square.grid.2x2")
                        .font(.callout.weight(.semibold))
                        .padding(.horizontal, 8)
                }
                .buttonStyle(.minimalBrand(theme: app.theme))
                .help("返回主菜单并清空课程 URL")
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(36)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func resultStat(_ label: String, value: Int, color: Color, icon: String) -> some View {
        VStack(spacing: 6) {
            Label("\(value)", systemImage: icon)
                .font(.title.weight(.bold))
                .monospacedDigit()
                .foregroundStyle(color)
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: - 底部任务条（与主体同底色，顶部发丝线）

    private var taskBar: some View {
        HStack(spacing: 16) {
            // 摘要：当前作业 / 计数
            VStack(alignment: .leading, spacing: 2) {
                Text(app.courseName.isEmpty ? (running ? "正在抓取…" : "就绪") : app.courseName)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(running ? "第 \(app.progressCurrent) / \(app.progressTotal) 个" : "\(app.selectedHomeworkIDs.count) 个已选作业")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .frame(width: 170, alignment: .leading)

            // 单一进度：大百分比 + 主题色填充
            if running {
                VStack(alignment: .leading, spacing: 7) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("\(app.progressPercent)%")
                            .font(.system(size: 24, weight: .bold, design: .rounded))
                            .monospacedDigit()
                            .foregroundStyle(.primary)
                            .contentTransition(.numericText())
                        Spacer()
                        runChip
                    }
                    ProgressBar(theme: app.theme, fraction: app.progressFraction)
                        .frame(height: 7)
                }
                .frame(maxWidth: .infinity)
                .transition(.opacity)
            } else {
                Spacer()
            }

            HStack(spacing: 10) {
                Button {
                    showDetails.toggle()
                } label: {
                    Image(systemName: "terminal")
                        .font(.body)
                }
                .buttonStyle(.minimalGhost)
                .popover(isPresented: $showDetails, arrowEdge: .top) {
                    detailsPopover
                }
                .help("运行详情")

                if running {
                    Button {
                        app.stopTask()
                    } label: {
                        Label("停止", systemImage: "stop.fill")
                            .font(.callout.weight(.medium))
                    }
                    .buttonStyle(.minimalGhostRed)
                }

                Button {
                    app.startSelected()
                } label: {
                    Label(running ? "抓取中…" : "开始抓取",
                          systemImage: running ? "clock.fill" : "play.fill")
                        .font(.callout.weight(.semibold))
                        .padding(.horizontal, 6)
                }
                .buttonStyle(.minimalBrand(theme: app.theme))
                .keyboardShortcut(.return, modifiers: [.command])
                // 引擎忙碌（列表加载中或抓取中）时禁用，防止加载未完成就启动导致误亮结果卡
                .disabled(app.isEngineBusy || app.selectedHomeworkIDs.isEmpty)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 16)
    }

    private var runChip: some View {
        HStack(spacing: 12) {
            if app.runOkCount > 0 {
                Chip(icon: "checkmark", count: app.runOkCount, color: Color(nsColor: .systemGreen))
            }
            if app.runFailCount > 0 {
                Chip(icon: "xmark", count: app.runFailCount, color: Color(nsColor: .systemRed))
            }
        }
    }

    /// 浮动运行详情面板（默认收起）
    private var detailsPopover: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Label("运行详情", systemImage: "terminal")
                    .font(.headline)
                Spacer()
                Button("仅复制报错") {
                    app.copyErrorLogsToClipboard()
                }
                .controlSize(.small)
                Button("复制日志") {
                    app.copyLogsToClipboard()
                }
                .controlSize(.small)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            Divider()

            LogView()
                .frame(width: 520, height: 300)
        }
        .frame(width: 520)
    }
}

/// 作业卡片：勾选框 + 标题 + 状态徽标；选中/悬停均有动效
private struct HomeworkRow: View {
    @Environment(AppState.self) private var app
    let item: HomeworkItem
    @State private var hovering = false

    private var theme: AppTheme { app.theme }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            CheckboxMark(isOn: selected, tint: theme.primary)
                .accessibilityLabel(item.title)
            Text(item.title)
                .font(.body)
                .foregroundStyle(.primary)
                .lineLimit(2)
            Spacer(minLength: 4)
            statusBadge
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(cardFill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(cardBorder, lineWidth: selected ? 1.5 : 1)
        )
        .shadow(color: theme.primary.opacity(selected ? 0.14 : 0), radius: 6, y: 2)
        .scaleEffect(hovering && !selected ? 1.015 : (selected ? 1.02 : 1))
        .animation(.spring(response: 0.4, dampingFraction: 0.72), value: selected)
        .animation(.easeOut(duration: 0.16), value: hovering)
        .contentShape(Rectangle())
        .onTapGesture { toggle() }
        .onHover { hovering = $0 }
    }

    private var selected: Bool { app.selectedHomeworkIDs.contains(item.id) }

    /// 卡片底色：选中→主题色浅染；悬停未选中→轻微提亮；默认→控件底色
    private var cardFill: Color {
        if selected { return theme.primary.opacity(0.10) }
        if hovering { return Color(nsColor: .controlBackgroundColor).opacity(0.7) }
        return Color(nsColor: .controlBackgroundColor)
    }

    /// 卡片描边：选中→主题色；悬停→分隔线加重；默认→弱分隔线
    private var cardBorder: Color {
        if selected { return theme.primary.opacity(0.65) }
        if hovering { return Color(nsColor: .separatorColor).opacity(0.8) }
        return Color(nsColor: .separatorColor).opacity(0.4)
    }

    private func toggle() {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.6)) {
            if selected {
                app.selectedHomeworkIDs.remove(item.id)
            } else {
                app.selectedHomeworkIDs.insert(item.id)
            }
        }
    }

    @ViewBuilder
    private var statusBadge: some View {
        if !item.status.isEmpty {
            HStack(spacing: 4) {
                Image(systemName: statusIcon)
                    .symbolEffect(.bounce, options: .nonRepeating, value: item.status)
                    .foregroundStyle(statusColor)
                    .font(.caption)
                Text(statusText)
                    .font(.caption)
                    .foregroundStyle(statusColor)
            }
            .accessibilityLabel(item.status)
            .help(item.status)
        }
    }

    private var statusIcon: String {
        switch item.status {
        case "completed": return "checkmark.circle.fill"
        case "failed": return "xmark.circle.fill"
        default: return "hourglass"
        }
    }
    private var statusText: String {
        switch item.status {
        case "completed": return "完成"
        case "failed": return "失败"
        default: return "处理中"
        }
    }
    private var statusColor: Color {
        switch item.status {
        case "completed": return Color(nsColor: .systemGreen)
        case "failed": return Color(nsColor: .systemRed)
        default: return .secondary
        }
    }
}

/// 扁平化复选框：选中态用主题色填充
private struct CheckboxMark: View {
    let isOn: Bool
    let tint: Color

    var body: some View {
        Image(systemName: isOn ? "checkmark" : "minus")
            .font(.system(size: 10, weight: .bold))
            .foregroundStyle(isOn ? .white : .clear)
            .frame(width: 17, height: 17)
            .background(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .fill(isOn ? tint : Color(nsColor: .textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .strokeBorder(isOn ? tint : Color(nsColor: .separatorColor), lineWidth: 1.2)
                    )
            )
            .transition(.scale)
    }
}

// MARK: - 进度条（主题色填充 + 流水高光，扁平化）

struct ProgressBar: View {
    let theme: AppTheme
    let fraction: Double
    @State private var phase: CGFloat = 0

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.primary.opacity(0.08))
                Capsule()
                    .fill(theme.primary)
                    .frame(width: max(geo.size.width * fraction, 14), height: .infinity)
                    .clipShape(Capsule())
                    .overlay(flowOverlay(size: geo.size))
            }
        }
        .animation(.easeOut(duration: 0.4), value: fraction)
        .onAppear { startFlow() }
        .onChange(of: fraction) { _, newVal in
            if newVal >= 1 { phase = 0 }
        }
    }

    /// 在已填充范围内流动的高光
    @ViewBuilder
    private func flowOverlay(size: CGSize) -> some View {
        let fillWidth = max(size.width * fraction, 14)
        GeometryReader { g in
            RoundedRectangle(cornerRadius: 8)
                .fill(
                    LinearGradient(colors: [
                        .white.opacity(0), .white.opacity(0.4), .white.opacity(0)
                    ], startPoint: .leading, endPoint: .trailing)
                )
                .frame(width: fillWidth * 0.5)
                .offset(x: phase * fillWidth)
        }
        .frame(width: fillWidth)
        .clipped()
    }

    private func startFlow() {
        guard fraction < 1 else { return }
        phase = -1
        withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) {
            phase = 2
        }
    }
}

/// 成功 / 失败计数小徽标
private struct Chip: View {
    let icon: String
    let count: Int
    let color: Color

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: icon)
                .font(.caption.weight(.bold))
                .foregroundStyle(color)
            Text("\(count)")
                .font(.callout.monospacedDigit().weight(.medium))
                .foregroundStyle(.primary)
        }
    }
}

// MARK: - 加载顶部：主题色细进度流水条（年轻化加载指示）

/// 加载作业列表时显示在顶部的细条：主题色不定长高光反复流动，替代传统转圈
private struct LoadingTopStrip: View {
    let theme: AppTheme
    @State private var phase: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.primary.opacity(0.08))
                Capsule()
                    .fill(
                        LinearGradient(colors: [theme.primary.opacity(0.5),
                                                theme.primary,
                                                theme.primary.opacity(0.5)],
                                       startPoint: .leading, endPoint: .trailing)
                    )
                    .frame(width: geo.size.width * 0.5)
                    .offset(x: phase * geo.size.width * 0.75)
            }
            .clipShape(Capsule())
        }
        .frame(height: 4)
        .onAppear {
            phase = -1
            withAnimation(.linear(duration: 1.1).repeatForever(autoreverses: false)) {
                phase = 1.4
            }
        }
    }
}

// MARK: - 骨架屏（加载作业列表的年轻化占位）

/// 骨架屏占位卡片列表：依次弹入模拟作业列表，加载完成后由外层淡出替换为真实卡片
private struct SkeletonCardList: View {
    @State private var appeared = false

    var body: some View {
        VStack(spacing: 9) {
            ForEach(0..<4, id: \.self) { i in
                SkeletonCard()
                    .padding(.horizontal, 20)
                    .transition(.asymmetric(
                        insertion: .opacity.combined(with: .move(edge: .bottom)).combined(with: .scale(scale: 0.98)),
                        removal: .opacity))
                    .animation(.spring(response: 0.5, dampingFraction: 0.72).delay(Double(i) * 0.05),
                               value: appeared)
            }
        }
        .padding(.vertical, 12)
        .onAppear { appeared = true }
    }
}

/// 单张骨架占位卡：勾选框 + 两行标题条 + 状态条，带流光扫过
private struct SkeletonCard: View {
    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 5)
                .fill(Color.primary.opacity(0.10))
                .frame(width: 17, height: 17)
            VStack(alignment: .leading, spacing: 9) {
                SkeletonBar(height: 12)
                SkeletonBar(height: 9)
                    .frame(width: 120)
            }
            Spacer(minLength: 8)
            SkeletonBar(height: 9)
                .frame(width: 56)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 13)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(Color(nsColor: .separatorColor).opacity(0.3), lineWidth: 1)
        )
    }
}

/// 灰色底 + 往复流光扫过的骨架条
private struct SkeletonBar: View {
    let height: CGFloat
    @State private var sweep: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Capsule().fill(Color.primary.opacity(0.10))
                Capsule()
                    .fill(LinearGradient(colors: [.clear, Color.white.opacity(0.55), .clear],
                                         startPoint: .leading, endPoint: .trailing))
                    .frame(height: height)
                    .offset(x: sweep * geo.size.width)
            }
            .clipShape(Capsule())
        }
        .frame(height: height)
        .onAppear {
            sweep = -1
            withAnimation(.linear(duration: 1.1).repeatForever(autoreverses: false)) {
                sweep = 1
            }
        }
    }
}

// MARK: - 自定义按钮样式（焕新界面·扁平风）

/// 通用悬停反馈：鼠标进入轻微放大 + 主题色柔和阴影（供所有按钮复用）。
struct HoverLift: ViewModifier {
    let shadowColor: Color
    @State private var hovering = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(hovering ? 1.04 : 1)
            .shadow(color: shadowColor.opacity(hovering ? 0.32 : 0), radius: 10, y: 4)
            .animation(.easeOut(duration: 0.15), value: hovering)
            .onHover { hovering = $0 }
    }
}

extension View {
    /// 统一给按钮加悬停「抬升 + 柔影」动效。
    func hoverLift(shadowColor: Color = .gray) -> some View {
        modifier(HoverLift(shadowColor: shadowColor))
    }
}

/// 主题色主按钮：平坦填充、圆角 8，悬停抬升、按下缩放
struct MinimalBrandButtonStyle: ButtonStyle {
    let theme: AppTheme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 9)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(configuration.isPressed ? theme.primary.opacity(0.85) : theme.primary)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .brightness(configuration.isPressed ? -0.06 : 0)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
            .hoverLift(shadowColor: theme.primary)
    }
}

extension ButtonStyle where Self == MinimalBrandButtonStyle {
    static func minimalBrand(theme: AppTheme) -> MinimalBrandButtonStyle { .init(theme: theme) }
}

/// 圆形次要图标按钮（运行详情等），悬停抬升
struct MinimalGhostButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.secondary)
            .frame(width: 34, height: 34)
            .contentShape(Circle())
            .background(
                Circle().fill(configuration.isPressed ? Color.primary.opacity(0.16) : Color.primary.opacity(0.06))
            )
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
            .hoverLift(shadowColor: .secondary)
    }
}

extension ButtonStyle where Self == MinimalGhostButtonStyle {
    static var minimalGhost: MinimalGhostButtonStyle { .init() }
}

/// 圆形深灰危险按钮（停止），悬停抬升
struct MinimalGhostRedButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(configuration.isPressed ? Color(nsColor: .systemRed).opacity(0.7) : Color(nsColor: .systemRed))
            .font(.callout)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color.red.opacity(configuration.isPressed ? 0.12 : 0.06))
            )
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
            .hoverLift(shadowColor: .red)
    }
}

extension ButtonStyle where Self == MinimalGhostRedButtonStyle {
    static var minimalGhostRed: MinimalGhostRedButtonStyle { .init() }
}

/// 描边次要按钮（选择目录/取消等），主题色描边，悬停抬升
struct MinimalOutlineButtonStyle: ButtonStyle {
    let theme: AppTheme

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(theme.primary)
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(configuration.isPressed ? theme.primary.opacity(0.12) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(theme.primary.opacity(0.55), lineWidth: 1)
            )
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
            .hoverLift(shadowColor: theme.primary)
    }
}

extension ButtonStyle where Self == MinimalOutlineButtonStyle {
    static func minimalOutline(theme: AppTheme) -> MinimalOutlineButtonStyle { .init(theme: theme) }
}

extension View {
    /// 主按钮样式：焕新用主题色填充，经典沿用系统 borderedProminent。
    @ViewBuilder
    func brandButtonStyle(active: Bool, theme: AppTheme) -> some View {
        if active {
            self.buttonStyle(.minimalBrand(theme: theme))
        } else {
            self.buttonStyle(.borderedProminent)
        }
    }

    /// 次要描边按钮样式：焕新用主题色描边，经典沿用系统 bordered。
    @ViewBuilder
    func outlineButtonStyle(active: Bool, theme: AppTheme) -> some View {
        if active {
            self.buttonStyle(.minimalOutline(theme: theme))
        } else {
            self.buttonStyle(.bordered)
        }
    }
}

// MARK: - 条件动效（兼容 macOS 14：bounce 仅 macOS 15+ 可用）

extension View {
    /// 仅当运行环境为 macOS 15+ 时应用 bounce 动效，老系统自动忽略（改为静态图标）。
    @ViewBuilder
    func bounceOnCompletion(_ bounce: Bool) -> some View {
        if #available(macOS 15.0, *) {
            if bounce {
                self.symbolEffect(.bounce, options: .nonRepeating)
            } else {
                self
            }
        } else {
            self
        }
    }
}