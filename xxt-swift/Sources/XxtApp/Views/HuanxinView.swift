import SwiftUI

/// 作业卡片几何参数：真实卡片与加载骨架屏共用同一套数值，
/// 保证「加载动画 → 最终卡片」过渡时尺寸、间距、圆角完全一致，避免视觉跳变与留白差异。
private let HW_CARD_H_PAD: CGFloat = 16     // 卡片水平内边距
private let HW_CARD_V_PAD: CGFloat = 14     // 卡片垂直内边距
private let HW_CARD_GAP: CGFloat = 12       // 卡片间距
private let HW_CARD_RADIUS: CGFloat = 11    // 卡片圆角
private let HW_ROW_ICON_GAP: CGFloat = 14   // 卡片内 勾选框↔内容 间距

/// v2.0「焕新界面」：简洁大方的高级审美（v2 定稿）
/// 扁平系统底色 + 发丝分隔线 + 充足留白；主题色仅用于主 CTA / 选中态 / 进度填充 / 状态强调。
/// 单页任务流：顶部课程 URL → 中间作业列表 → 底部任务条；结果态覆盖主区为结果卡片。
/// 日志降级为右下角「运行详情」浮动面板，默认收起。
struct HuanxinView: View {
    @Environment(AppState.self) private var app
    @State private var showDetails = false
    @State private var searchText = ""
    /// 搜索框焦点态：⌘F 聚焦、⌘A 全选、⌘⇧A 清空（配合隐藏快捷键按钮）
    @FocusState private var searchFocused: Bool
    /// 顶栏状态点的呼吸脉冲进度（true 后循环外扩淡出）
    @State private var statusPulse = false
    /// 控件忙碌呼吸：加载 / 开始抓取按钮在引擎忙碌时的柔和缩放呼吸
    @State private var ctlPulse = false
    /// 空闲面板图标上下浮动的偏移
    @State private var idleFloat: CGFloat = 0
    /// 抓取中是否暂回作业列表（收起进度面板，抓取继续在后台进行）
    @State private var showListDuringRun = false
    /// 任务条进度模块悬停态（提示可点击回到进度面板）
    @State private var progressHover = false

    /// 引导流程阶段：登录后默认教程卡片 → 课程列表 → 作业列表（后续走现有流程）
    private enum Phase: String, Equatable { case tutorial, course, works }
    @State private var phase: Phase = .tutorial

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
            if phase != .tutorial { Divider() }

            ZStack {
                mainArea
                    // 抓取中默认收起作业列表；点「返回作业列表」可临时切回，抓取继续在后台进行
                    .opacity((phase == .works && running && !showListDuringRun) ? 0 : 1)
                if phase == .works && finished {
                    resultCard
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
                if phase == .works && running && !showListDuringRun {
                    runningPanel
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }
            }
            .animation(.smooth(duration: 0.45), value: finished)
            .animation(.smooth(duration: 0.4), value: running)
            .animation(.smooth(duration: 0.4), value: showListDuringRun)
            .animation(.smooth(duration: 0.35), value: loading)
            .animation(.smooth(duration: 0.35), value: phase)

            if phase != .tutorial { Divider() }
            taskBar
        }
        .tint(app.theme.primary)
        // 运行结束时自动复位「返回作业列表」，下次抓取仍默认展示进度面板
        .onChange(of: app.isRunning) { _, isRunning in
            if !isRunning { showListDuringRun = false }
        }
        // 引擎忙碌（加载作业 / 抓取中）时让控件开启柔和呼吸动效
        .onAppear { if app.isEngineBusy { startCtlPulse() } }
        .onChange(of: app.isEngineBusy) { _, busy in
            if busy { startCtlPulse() }
        }
        // 快捷键：⌘F 聚焦搜索，⌘A 全选，⌘⇧A 清空（隐藏按钮，保持窗口级可用）。
        // 注意：overlay 默认居中对齐，按钮必须 opacity(0) + 零尺寸 + 锚定左上，
        // 否则 macOS 会把带系统边框的空按钮渲染到界面正中。
        .overlay(alignment: .topLeading) {
            HStack(spacing: 0) {
                Button { searchFocused = true } label: {}
                    .keyboardShortcut("f", modifiers: .command)
                    .opacity(0)
                    .allowsHitTesting(false)
                    .frame(width: 0, height: 0)
                Button {
                    if app.isRunning {
                        // 运行中只追加未抓取作业（禁移除）
                        app.addRunningHomeworks(filteredHomeworks.map(\.id))
                    } else {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                            app.selectedHomeworkIDs.formUnion(filteredHomeworks.map(\.id))
                        }
                    }
                } label: {}
                    .keyboardShortcut("a", modifiers: .command)
                    .opacity(0)
                    .allowsHitTesting(false)
                    .frame(width: 0, height: 0)
                Button {
                    guard !app.isRunning else { return } // 抓取中锁定清空
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                        app.selectedHomeworkIDs.removeAll()
                    }
                } label: {}
                    .keyboardShortcut("a", modifiers: [.command, .shift])
                    .opacity(0)
                    .allowsHitTesting(false)
                    .frame(width: 0, height: 0)
            }
            .fixedSize()
        }
    }

    /// 控件忙碌呼吸：柔和缩放 + 透明度循环，替代传统转圈加载
    private func startCtlPulse() {
        withAnimation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true)) {
            ctlPulse = true
        }
    }

    // MARK: - 顶部：品牌 + 状态（无装饰，留白克制）

    private var header: some View {
        HStack {
            Spacer()
            HStack(spacing: 6) {
                statusDot
                Text(statusText)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(.secondary)
                    .animation(.easeInOut(duration: 0.25), value: statusText)
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

    /// 状态色：运行=主题色，加载=琥珀，就绪=绿
    private var statusColor: Color {
        if running { return app.theme.primary }
        if loading { return .orange }
        return Color.green
    }

    /// 忙碌时为真（驱动的呼吸脉冲）
    private var statusBusy: Bool { running || loading }

    /// 顶栏状态点：忙碌时外圈呈「外扩淡出」呼吸，静态完成态仅实心点。
    /// 颜色切换加过渡动画；外圈在忙碌→静态时平滑淡出缩小。
    private var statusDot: some View {
        ZStack {
            if statusBusy {
                Circle()
                    .stroke(statusColor, lineWidth: 1.2)
                    .frame(width: 12, height: 12)
                    .scaleEffect(statusPulse ? 2.4 : 1)
                    .opacity(statusPulse ? 0 : 0.8)
                    .transition(.scale(scale: 0.6).combined(with: .opacity))
            }
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
        }
        .frame(width: 18, height: 18)
        // 颜色渐变过渡
        .animation(.easeInOut(duration: 0.3), value: statusColor)
        // 外圈出现/消失平滑
        .animation(.easeOut(duration: 0.25), value: statusBusy)
        .onAppear {
            if statusBusy { startStatusPulse() }
        }
        .onChange(of: statusBusy) { _, busy in
            if busy { startStatusPulse() }
        }
    }

    /// 起始一次呼吸外扩，repeatForever 令其循环
    private func startStatusPulse() {
        statusPulse = false
        withAnimation(.easeOut(duration: 1.3).repeatForever(autoreverses: false)) {
            statusPulse = true
        }
    }

    // MARK: - 中间主区域

    private var mainArea: some View {
        Group {
            switch phase {
            case .tutorial:
                tutorialView
            case .course:
                courseSelectView
            case .works:
                VStack(spacing: 0) {
                    courseRow
                    listHeader
                    listBody
                }
            }
        }
    }

    /// ① 选择课程：账号课程选择（主）+ 粘贴课程 URL（兜底）+ 主题色加载按钮（平坦、无包裹卡）
    private var courseRow: some View {
        HStack(spacing: 10) {
            Text("① 选择课程")
                .font(.callout.weight(.medium))
                .foregroundStyle(.secondary)
            courseButton
            // URL 兜底输入：选中课程会自动填充；也可手动粘贴课程链接后用「加载」读取
            HStack(spacing: 6) {
                TextField("或粘贴课程 URL", text: Bindable(app).settings.courseURL)
                    .textFieldStyle(.plain)
                    .font(.body)
                    .submitLabel(.go)
                    .onSubmit { app.loadHomeworks() }
                // 一键清空长链接：比手动全选删除更省事
                if !app.settings.courseURL.isEmpty {
                    Button {
                        app.settings.courseURL = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 14))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("清空链接")
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color(nsColor: .textBackgroundColor))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1)
                    )
            )
            Button {
                guard !app.isEngineBusy else { return }
                app.loadHomeworks()
            } label: {
                Text(app.isEngineBusy ? "加载中…" : "加载")
                    .font(.callout.weight(.semibold))
                    .padding(.horizontal, 6)
                    // 忙碌时的柔和缩放呼吸，替代传统转圈等待
                    .scaleEffect(app.isEngineBusy ? (ctlPulse ? 0.96 : 1.0) : 1.0)
                    .opacity(app.isEngineBusy ? (ctlPulse ? 0.6 : 1.0) : 1.0)
            }
            .buttonStyle(.minimalBrand(theme: app.theme, disabled: app.isEngineBusy))
            .disabled(app.isEngineBusy)
            .help(app.isEngineBusy ? "正在加载，请稍候…" : "加载作业列表")
        }
        .padding(.horizontal, 20)
        .padding(.top, 14)
    }

    /// 「选择课程」文案：已选课程显示标题，否则提示选择
    private var coursePickerLabel: String {
        if let c = app.selectedCourse { return c.title }
        return "选择课程…"
    }

    /// 「选择课程」入口（作业列表顶部）：展示当前所选课程，点击回到课程列表重新选择。
    private var courseButton: some View {
        Button {
            withAnimation(.smooth(duration: 0.35)) { phase = .course }
        } label: {
            HStack(spacing: 8) {
                coverDot
                Text(coursePickerLabel)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 180, alignment: .leading)
                Image(systemName: "chevron.down")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            .font(.callout.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color(nsColor: .textBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(app.selectedCourse == nil ? Color(nsColor: .separatorColor) : app.theme.primary.opacity(0.55),
                                  lineWidth: app.selectedCourse == nil ? 1 : 1.2)
            )
            .hoverLift(shadowColor: app.theme.primary)
        }
        .buttonStyle(.plain)
        .disabled(app.isEngineBusy)
        .help(app.selectedCourse == nil ? "点击选择要抓取的课程" : "当前所选课程：\(coursePickerLabel)，点此更换")
    }

    /// 已选课程的封面色圆点；未选时用灰色书本占位
    private var coverDot: some View {
        Group {
            if let c = app.selectedCourse {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(courseTint(c))
                    .frame(width: 16, height: 16)
                    .overlay(
                        Text(String(c.title.prefix(1)))
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.white)
                    )
            } else {
                Image(systemName: "square.grid.2x2")
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(app.theme.primary)
            }
        }
    }

    // MARK: - 教程卡片（登录后默认引导，第一步为「选择课程」）

    /// 默认阶段：教程卡片 + 下方「开始」按钮。点「开始」后进入课程列表。
    private var tutorialView: some View {
        // 加大主体元素、收紧留白，让引导更醒目清晰
        VStack(spacing: 34) {
            VStack(spacing: 18) {
                Image(systemName: "graduationcap.fill")
                    .font(.system(size: 62, weight: .medium))
                    .foregroundStyle(app.theme.primary)
                    .symbolEffect(.bounce, options: .nonRepeating, value: tutorialTick)
                Text("三步搞定作业抓取")
                    .font(.largeTitle.weight(.bold))
                    .foregroundStyle(.primary)
                Text("从学习通账号选择课程，勾选作业，一键输出 Word 文档")
                    .font(.body.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            HStack(spacing: 22) {
                IdleStep(number: "1", icon: "square.grid.2x2", title: "选择课程",
                         subtitle: "从账号选要抓取的课程", theme: app.theme)
                stepArrow
                IdleStep(number: "2", icon: "checklist", title: "勾选作业",
                         subtitle: "选择要抓取的内容", theme: app.theme)
                stepArrow
                IdleStep(number: "3", icon: "play.fill", title: "开始抓取",
                         subtitle: "输出 Word 文档", theme: app.theme)
            }
            Button {
                startOnboarding()
            } label: {
                Text("开始")
                    .font(.callout.weight(.semibold))
                    .frame(minWidth: 230)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.minimalBrand(theme: app.theme))
            .help("进入课程列表，选择要抓取的课程")

            Button {
                app.openHelpDocument()
            } label: {
                Text("帮助文档")
                    .font(.callout.weight(.medium))
                    .frame(minWidth: 150)
                    .padding(.vertical, 3)
            }
            .outlineButtonStyle(active: app.uiMode == .huanxin, theme: app.theme)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(nsColor: .quaternarySystemFill))
            )
            .help("打开使用帮助文档")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            tutorialTick.toggle()
        }
    }

    /// 触发教程图标弹动的一次性 tick
    @State private var tutorialTick = false
    // 课程卡片网格的入场动效开关：false→true 触发卡片依次弹入
    @State private var courseEntrance = false

    /// 点「开始」：进入课程列表；若尚未加载课程则自动拉取
    private func startOnboarding() {
        withAnimation(.smooth(duration: 0.35)) { phase = .course }
        if app.courses.isEmpty && !app.isLoadingCourses {
            app.loadCourses()
        }
    }

    // MARK: - 课程列表（选课程阶段，主区域卡片网格）

    private var courseColumns: [GridItem] {
        [GridItem(.adaptive(minimum: 196, maximum: 320), spacing: 16)]
    }

    /// 课程排序：进行中课程在前，已结束课程置底。
    private var sortedCourses: [CourseItem] {
        app.courses.sorted { a, b in
            if a.ended != b.ended { return !a.ended }
            return a.title.localizedStandardCompare(b.title) == .orderedAscending
        }
    }

    /// 选课程阶段：标题栏 + 课程卡片网格。点选卡片即选中并进入作业列表。
    private var courseSelectView: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Text("① 选择课程")
                    .font(.callout.weight(.medium))
                    .foregroundStyle(.secondary)
                if !app.courses.isEmpty {
                    Text("共 \(app.courses.count) 门")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
                Spacer()
                if app.isLoadingCourses && app.courses.isEmpty {
                    HStack(spacing: 6) {
                        Image(systemName: "arrow.clockwise")
                            .rotationEffect(.degrees(app.isLoadingCourses ? 360 : 0))
                            .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: app.isLoadingCourses)
                        Text("加载中…")
                    }
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(.secondary)
                }
                Button("刷新") {
                    app.loadCourses()
                }
                .buttonStyle(.minimalOutline(theme: app.theme))
                .disabled(app.isEngineBusy)
                .help("重新从学习通账号拉取课程列表")
            }
            .padding(.horizontal, 20)
            .padding(.top, 14)
            .padding(.bottom, 12)
            Divider()
            courseListContent
        }
    }

    @ViewBuilder
    private var courseListContent: some View {
        if app.isLoadingCourses && app.courses.isEmpty {
            VStack(spacing: 0) {
                // 顶部细流光提示「正在加载课程…」
                LoadingTopStrip(theme: app.theme)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                SkeletonCourseList(theme: app.theme)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        } else if app.courses.isEmpty {
            VStack(spacing: 14) {
                Image(systemName: "books.vertical")
                    .font(.system(size: 40, weight: .light))
                    .foregroundStyle(.secondary)
                Text("还没有加载到课程")
                    .font(.callout.weight(.medium))
                    .foregroundStyle(.secondary)
                Button {
                    app.loadCourses()
                } label: {
                    Label("加载课程列表", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.minimalBrand(theme: app.theme))
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVGrid(columns: courseColumns, spacing: 14) {
                    ForEach(Array(sortedCourses.enumerated()), id: \.element.id) { index, course in
                        CourseCard(course: course, isSelected: app.selectedCourse?.id == course.id) {
                            pickCourse(course)
                        }
                        .transition(.asymmetric(
                            insertion: .opacity.combined(with: .scale(scale: 0.9)).combined(with: .move(edge: .bottom)),
                            removal: .opacity))
                        .animation(.spring(response: 0.55, dampingFraction: 0.78).delay(Double(index) * 0.045),
                                   value: courseEntrance)
                    }
                }
                .padding(20)
            }
            .onAppear {
                // 进入课程列表时触发卡片依次弹入（仅在首次出现时）
                guard !courseEntrance else { return }
                withAnimation { courseEntrance = true }
            }
        }
    }

    /// 点选课程：记录选中 → 进入作业列表 → 自动加载该课作业列表（衔接「② 选择作业」）
    private func pickCourse(_ course: CourseItem) {
        app.selectCourse(course)
        withAnimation(.smooth(duration: 0.35)) { phase = .works }
        app.loadHomeworks()
    }

    private var listHeader: some View {
        VStack(spacing: 10) {
            HStack {
                Text("② 选择作业")
                    .font(.callout.weight(.medium))
                    .foregroundStyle(.secondary)
                Spacer()
                if !app.homeworks.isEmpty {
                    Text("已选 \(app.selectedHomeworkIDs.count) / \(filteredHomeworks.count)")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                    Button("全选") {
                        if app.isRunning {
                            // 运行中只追加未抓取作业（禁移除）
                            app.addRunningHomeworks(filteredHomeworks.map(\.id))
                        } else {
                            withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                                app.selectedHomeworkIDs.formUnion(filteredHomeworks.map(\.id))
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Color.primary.opacity(0.06))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1)
                    )
                    .hoverLift(shadowColor: .secondary, enabled: !isAllSelected)
                    .disabled(isAllSelected)
                    Button("清空") {
                        withAnimation(.spring(response: 0.4, dampingFraction: 0.7)) {
                            app.selectedHomeworkIDs.removeAll()
                        }
                    }
                    .buttonStyle(.plain)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(Color.primary.opacity(0.06))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1)
                    )
                    .hoverLift(shadowColor: .secondary, enabled: !app.selectedHomeworkIDs.isEmpty)
                    .disabled(app.isRunning || app.selectedHomeworkIDs.isEmpty)
                }
            }
            if !app.homeworks.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "magnifyingglass")
                        .foregroundStyle(.secondary)
                    TextField("搜索作业标题…", text: $searchText)
                        .textFieldStyle(.plain)
                        .font(.callout)
                        .focused($searchFocused)
                    // 正在搜索时提供一键清除，符合系统搜索框习惯
                    if !searchText.isEmpty {
                        Button {
                            searchText = ""
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("清除搜索")
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Color(nsColor: .textBackgroundColor))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .strokeBorder(Color(nsColor: .separatorColor), lineWidth: 1)
                        )
                )
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 8)
        .padding(.bottom, 12)
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
            .transition(.opacity.combined(with: .scale(scale: 0.97)))
            .animation(.easeInOut(duration: 0.25), value: filteredHomeworks.isEmpty)
        } else {
            ScrollView {
                LazyVStack(spacing: HW_CARD_GAP) {
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
                        .font(.callout.weight(.medium))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 10)
            }
            SkeletonCardList(theme: app.theme)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    /// 空闲：URL 引导（含常驻三步流程帮助，无需输入即可了解操作路径）
    private var idlePanel: some View {
        VStack(spacing: 22) {
            VStack(spacing: 12) {
                Image(systemName: "square.stack.3d.up")
                    .font(.system(size: 48, weight: .medium))
                    .foregroundStyle(.secondary)
                    .offset(y: idleFloat)
                    .animation(.easeInOut(duration: 2.6).repeatForever(autoreverses: true),
                               value: idleFloat)
                Text("暂无作业")
                    .font(.title2.weight(.semibold))
                    .foregroundStyle(.primary)
                Text("在上方选择课程或粘贴课程 URL，然后点击「加载」")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.secondary)
            }
            // 常驻三步流程引导：不依赖“已输入 URL”，首开即可见
            HStack(spacing: 12) {
                IdleStep(number: "1", icon: "square.grid.2x2", title: "选择课程",
                         subtitle: "从账号选要抓取的课程", theme: app.theme)
                stepArrow
                IdleStep(number: "2", icon: "checklist", title: "勾选作业",
                         subtitle: "选择要抓取的内容", theme: app.theme)
                stepArrow
                IdleStep(number: "3", icon: "play.fill", title: "开始抓取",
                         subtitle: "输出 Word 文档", theme: app.theme)
            }
            .padding(.top, 6)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.bottom, 40)
        .onAppear { idleFloat = -6 }
    }

    private var stepArrow: some View {
        Image(systemName: "chevron.right")
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(.tertiary)
            .symbolRenderingMode(.monochrome)
    }

    /// 当前正在抓取的作业标题（按行级状态识别“进行中”的作业，无则回退为“正在抓取”）
    private var focusCurrentTitle: String? {
        app.homeworks.first {
            app.selectedHomeworkIDs.contains($0.id) && isActiveStatus($0.status)
        }?.title
    }

    /// 任务条摘要标题：抓取中优先显示“具体在抓哪份作业”，否则显示课程名或就绪占位
    private var runningTitle: String {
        if running {
            return focusCurrentTitle ?? (app.courseName.isEmpty ? "正在抓取…" : app.courseName)
        }
        return app.courseName.isEmpty ? "就绪" : app.courseName
    }

    /// 抓取中「第 x / n 个」计数文案：进度事件未到达（total 未知）时，用已选作业数兜底，避免显示刺眼的“第 0 / 0 个”。
    /// 语义：进度完成数 progressCurrent 的“下一个”即当前正在抓的序号（从 1 起）。
    private var progressCountText: String {
        let total = app.progressTotal > 0 ? app.progressTotal : app.selectedHomeworkIDs.count
        guard total > 0 else { return "正在抓取…" }
        let current = min(app.progressCurrent + 1, total)
        return "第 \(current) / \(total) 个"
    }

    private func isActiveStatus(_ s: String) -> Bool {
        !s.isEmpty && s != "completed" && s != "failed"
    }

    /// 抓取中：收起作业列表，专注展示已选作业的实时进度
    private var runningPanel: some View {
        let selected = app.homeworks.filter { app.selectedHomeworkIDs.contains($0.id) }
        return VStack(spacing: 0) {
            // 当前作业标题 + 合计
            VStack(spacing: 6) {
                Text(focusCurrentTitle ?? "正在抓取…")
                    .font(.title3.weight(.semibold))
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text("成功 \(app.runOkCount) · 失败 \(app.runFailCount) · 共 \(selected.count) 个")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .padding(.top, 28)
            .padding(.bottom, 18)

            // 总进度：大百分比 + 主题色填充
            Text("\(app.progressPercent)%")
                .font(.system(size: 56, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(.primary)
                .contentTransition(.numericText())
                .padding(.bottom, 12)

            ProgressBar(theme: app.theme, fraction: app.progressFraction, animated: false)
                .frame(height: 10)
                .padding(.horizontal, 64)

            // 已选作业行级实时状态
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(selected) { item in
                        RunningRow(item: item, theme: app.theme)
                    }
                }
                .padding(.horizontal, 48)
                .padding(.vertical, 22)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .clipped()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        // 左上角：返回作业列表（收起进度面板，抓取在后台继续）
        .overlay(alignment: .topLeading) {
            Button {
                withAnimation(.smooth(duration: 0.4)) { showListDuringRun = true }
            } label: {
                Label("返回作业列表", systemImage: "chevron.left")
                    .font(.callout.weight(.medium))
            }
            .buttonStyle(.minimalOutline(theme: app.theme))
            .padding(.top, 16)
            .padding(.leading, 20)
            .help("收起进度面板，返回作业列表（抓取在后台继续）")
        }
    }

    /// 抓取中：单个已选作业的行级状态徽标（等待·进行中·成功·失败）
    private struct RunningRow: View {
        let item: HomeworkItem
        let theme: AppTheme
        @State private var pulse = false

        var body: some View {
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 12) {
                    statusIcon
                    Text(item.title)
                        .font(.callout.weight(.medium))
                        .lineLimit(1)
                        .truncationMode(.middle)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    statusLabel
                }
                // 进行中的作业：行级微进度条 + 百分比，直观反馈单作业内部进度
                if isInProgress {
                    ProgressBar(theme: theme, fraction: item.progress)
                        .frame(height: 4)
                        .frame(maxWidth: .infinity)
                    HStack {
                        Spacer()
                        Text("\(item.progressPercent)%")
                            .font(.caption2.monospacedDigit().weight(.medium))
                            .foregroundStyle(theme.primary)
                            .contentTransition(.numericText())
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
        }

        /// 进行中（等待空白不算）：status 非空且非成功/失败
        private var isInProgress: Bool {
            item.status != "" && item.status != "completed" && item.status != "failed"
        }

        @ViewBuilder
        private var statusIcon: some View {
            switch item.status {
            case "completed":
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(Color(nsColor: .systemGreen))
            case "failed":
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 16))
                    .foregroundStyle(Color(nsColor: .systemRed).opacity(0.9))
            case "":
                // 等待处理：灰点
                Circle().fill(Color.secondary.opacity(0.3)).frame(width: 12, height: 12)
            default:
                // 进行中：主题色呼吸点（年轻化，非传统转圈）
                Circle()
                    .fill(theme.primary)
                    .frame(width: 12, height: 12)
                    .scaleEffect(pulse ? 1.45 : 0.8)
                    .opacity(pulse ? 0.35 : 1)
                    .onAppear {
                        withAnimation(.easeInOut(duration: 0.85).repeatForever(autoreverses: true)) {
                            pulse = true
                        }
                    }
            }
        }

        @ViewBuilder
        private var statusLabel: some View {
            switch item.status {
            case "completed":
                Text("成功").font(.footnote.weight(.semibold)).foregroundStyle(Color(nsColor: .systemGreen))
            case "failed":
                Text("失败").font(.footnote.weight(.semibold)).foregroundStyle(Color(nsColor: .systemRed))
            case "":
                Text("等待").font(.footnote).foregroundStyle(.secondary)
            default:
                Text("进行中").font(.footnote.weight(.semibold)).foregroundStyle(theme.primary)
            }
        }
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
            // 主题渐变细线点缀：呼应主 CTA 与进度条的主题色联动
            Capsule()
                .fill(LinearGradient(colors: app.theme.gradient,
                                     startPoint: .leading, endPoint: .trailing))
                .frame(width: 116, height: 4)
                .offset(y: -6)
            // 结果卡三栏复盘：静态三栏（图片失败恒占位），避免成功/失败未触发时卡片跳动
            HStack(spacing: 32) {
                resultStat("成功", value: app.runOkCount, color: Color(nsColor: .systemGreen), icon: "checkmark.circle.fill")
                resultStat("失败", value: app.runFailCount, color: Color(nsColor: .systemRed), icon: "xmark.circle.fill")
                resultStat("图片失败", value: app.runImageFailCount,
                           color: Color(nsColor: .systemOrange), icon: "photo.badge.exclamationmark",
                           accent: app.runImageFailCount > 0)
            }
            // 抓取耗时：仅在本次确实发起过抓取且已结束时展示
            if !app.runDurationText.isEmpty {
                HStack(spacing: 7) {
                    Image(systemName: "clock.fill")
                        .font(.system(size: 15))
                        .foregroundStyle(app.theme.primary)
                    Text("抓取耗时")
                        .foregroundStyle(.secondary)
                    Text(app.runDurationText)
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(.primary)
                        .monospacedDigit()
                }
                .font(.callout)
                .padding(.top, -10)
            }
            // 结果卡操作：三按钮整齐单行排列，主操作主题色、次操作描边弱化、高度一致
            HStack(spacing: 12) {
                if !app.lastOutputDir.isEmpty {
                    Button {
                        app.openLastOutput()
                    } label: {
                        Label("打开输出目录", systemImage: "folder")
                            .font(.callout.weight(.medium))
                    }
                    .buttonStyle(.minimalOutline(theme: app.theme))
                    .help("打开本次抓取的输出目录")
                }

                Button {
                    withAnimation(.smooth(duration: 0.45)) {
                        app.backToMainMenu()
                        // backToMainMenu 只复位数据；需切回课程列表阶段，否则仍停留在空作业列表页
                        phase = .course
                    }
                } label: {
                    Label("抓取其他课程作业", systemImage: "square.grid.2x2")
                        .font(.callout.weight(.medium))
                }
                .buttonStyle(.minimalOutline(theme: app.theme))
                .help("返回课程列表，重新选择其他课程")

                Button {
                    withAnimation(.smooth(duration: 0.45)) { app.backToSelection() }
                } label: {
                    Label("继续抓取", systemImage: "arrow.uturn.backward")
                        .font(.callout.weight(.semibold))
                }
                .buttonStyle(.minimalBrand(theme: app.theme))
                .help("回到作业选择页面，重新选择后再次抓取")
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(36)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func resultStat(_ label: String, value: Int, color: Color, icon: String, accent: Bool = true, dimmed: Bool = false) -> some View {
        // accent=false 且值非强调时：整栏灰调，便于甄别“没有异常”的静默项
        let effectiveColor = (accent && !dimmed) ? color : Color.secondary.opacity(0.55)
        return VStack(spacing: 6) {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .font(.system(size: 28))
                    .foregroundStyle(effectiveColor)
                CountUpNumber(value: value, textStyle: .largeTitle, color: effectiveColor, size: 34)
            }
            Text(label)
                .font(.callout.weight(.semibold))
                .foregroundStyle(.secondary)
        }
    }

    /// 开始抓取按钮的文案/图标：按状态区分，禁用时也能一眼看出原因
    private var startButtonState: (title: String, icon: String) {
        if running { return ("抓取中…", "clock.fill") }
        if loading { return ("加载中…", "arrow.trianglehead.2.clockwise.rotate.90") }
        if app.selectedHomeworkIDs.isEmpty { return ("请选择作业", "checkmark.circle.badge.questionmark") }
        return ("开始抓取", "play.fill")
    }

    /// 开始抓取按钮禁用时的悬浮提示
    private var startButtonHelp: String {
        if loading { return "作业列表加载中，请稍候后再抓取" }
        if app.selectedHomeworkIDs.isEmpty { return "请先勾选要抓取的作业" }
        return "开始抓取选中的作业"
    }

    // MARK: - 底部任务条（与主体同底色，顶部发丝线）

    private var taskBar: some View {
        HStack(spacing: 16) {
            // 摘要：当前作业标题 / 计数（仅作业阶段显示；教程/选课阶段整行隐藏，只留右下角运行详情）
            if phase == .works {
                VStack(alignment: .leading, spacing: 2) {
                    Text(runningTitle)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text(running ? progressCountText : "\(app.selectedHomeworkIDs.count) 个已选作业")
                        .font(.callout.weight(.medium))
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                }
                .frame(width: 240, alignment: .leading)
            }

            // 单一进度：大百分比 + 主题色填充
            // 点「返回作业列表」收起的进度面板可由此重新唤起，回到抓取过程页面
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
                        // 暂回作业列表时用一只小箭头提示：点击此进度模块可回到抓取过程页面
                        if showListDuringRun {
                            Image(systemName: "arrow.up.left.circle.fill")
                                .font(.system(size: 13))
                                .foregroundStyle(progressHover ? app.theme.primary : Color.secondary.opacity(0.7))
                                .help("点击回到抓取过程页面")
                        }
                    }
                    ProgressBar(theme: app.theme, fraction: app.progressFraction, animated: false)
                        .frame(height: 7)
                }
                .frame(maxWidth: .infinity)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.smooth(duration: 0.4)) { showListDuringRun = false }
                }
                .onHover { hovering in
                    withAnimation(.easeOut(duration: 0.15)) { progressHover = hovering }
                }
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(progressHover ? app.theme.primary.opacity(0.07) : Color.clear)
                )
                .padding(.vertical, 6)
                .padding(.horizontal, 10)
                .help(showListDuringRun ? "点击回到抓取过程页面" : "抓取进度")
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
                        app.stopAction()
                    } label: {
                        Label(app.stopArmed ? "确认停止" : "停止", systemImage: "stop.fill")
                            .font(.callout.weight(app.stopArmed ? .bold : .medium))
                    }
                    .buttonStyle(.minimalGhostRed)
                    .animation(.easeInOut(duration: 0.18), value: app.stopArmed)
                }

                // 非运行时才显示「开始抓取」主按钮；运行时由「停止」独占，避免“抓取中…”灰显按钮造成语义冗余；
                // 教程/选课阶段无作业可抓，隐藏以保持底部仅剩运行详情圆钮
                if !running && phase == .works {
                    Button {
                        app.startSelected()
                    } label: {
                        Label(startButtonState.title,
                          systemImage: startButtonState.icon)
                        .font(.body.weight(.semibold))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 3)
                        // 引擎忙碌（加载中）时的柔和呼吸，替代传统转圈等待
                        .scaleEffect(app.isEngineBusy ? (ctlPulse ? 0.97 : 1.0) : 1.0)
                        .opacity(app.isEngineBusy ? (ctlPulse ? 0.7 : 1.0) : 1.0)
                }
                    .buttonStyle(.minimalBrand(theme: app.theme,
                                               disabled: app.isEngineBusy || app.selectedHomeworkIDs.isEmpty,
                                               gradient: app.theme.gradient))
                    .keyboardShortcut(.return, modifiers: [.command])
                    // 引擎忙碌（列表加载中）或无勾选时禁用；样式随禁用态置灰，避免“点了没反应”的困惑
                    .disabled(app.isEngineBusy || app.selectedHomeworkIDs.isEmpty)
                    .help(startButtonHelp)
                }
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

/// 作业卡片：勾选框 + 标题 + 状态徽标；与骨架屏卡片同尺寸、同样式，仅保留极简选中反馈
private struct HomeworkRow: View {
    @Environment(AppState.self) private var app
    let item: HomeworkItem

    private var theme: AppTheme { app.theme }
    /// 本会话内已抓取成功的印记（刷新列表后仍保留）
    private var scraped: Bool { app.completedHomeworkIds.contains(item.id) }

    var body: some View {
        HStack(alignment: .center, spacing: HW_ROW_ICON_GAP) {
            CheckboxMark(isOn: selected, tint: theme.primary)
                .accessibilityLabel(item.title)
            Text(item.title)
                .font(.callout.weight(.medium))
                .foregroundStyle(.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
                .opacity(app.isRunning && selected ? 0.72 : 1)
            if app.isRunning && selected {
                Image(systemName: "lock.fill")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .help("抓取中已锁定作业选择")
                    .transition(.scale.combined(with: .opacity))
            }
            Spacer(minLength: 4)
            statusBadge
        }
        .padding(.horizontal, HW_CARD_H_PAD)
        .padding(.vertical, HW_CARD_V_PAD)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: HW_CARD_RADIUS, style: .continuous)
                .fill(cardFill)
        )
        .overlay(
            RoundedRectangle(cornerRadius: HW_CARD_RADIUS, style: .continuous)
                .strokeBorder(cardBorder, lineWidth: selected ? 1.5 : 1)
        )
        // 「已抓」印记：左侧主题色描边，「从左边滑入」的绘制动效（spring）
        .overlay(alignment: .leading) {
            Capsule()
                .fill(theme.primary.opacity(0.8))
                .frame(width: 3.5)
                .padding(.vertical, 11)
                .scaleEffect(x: scraped ? 1 : 0, anchor: .leading)
                .animation(.spring(response: 0.5, dampingFraction: 0.62), value: scraped)
        }
        .contentShape(Rectangle())
        .onTapGesture { toggle() }
        // 勾选/印记/锁定变化时的柔和弹性衔接，选中圆角描边与锁定图标随之过渡
        .animation(.spring(response: 0.42, dampingFraction: 0.78), value: selected)
        .animation(.spring(response: 0.42, dampingFraction: 0.78), value: app.isRunning)
    }

    private var selected: Bool { app.selectedHomeworkIDs.contains(item.id) }

    /// 卡片底色：选中→极淡主题色染；否则与骨架屏完全一致（controlBackgroundColor）
    private var cardFill: Color {
        if selected { return theme.primary.opacity(0.08) }
        return Color(nsColor: .controlBackgroundColor)
    }

    /// 卡片描边：选中→主题色半透明细边；否则与骨架屏一致（分隔线 0.4 透明度）
    private var cardBorder: Color {
        if selected { return theme.primary.opacity(0.55) }
        return Color(nsColor: .separatorColor).opacity(0.4)
    }

    private func toggle() {
        // 运行中：只允许「新增未抓取作业」，禁止移除/反选运行中的作业。
        // 引擎已升级为动态队列，新增的作业会自动进入抓取队列并在本轮处理；
        // 反选会造成「引擎已抓却不再计入结果」的错位，故运行期一律禁止。
        if app.isRunning {
            guard !selected else { return }
            app.addRunningHomeworks([item.id])
            return
        }
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
                    .font(.callout)
                Text(statusText)
                    .font(.callout.weight(.semibold))
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

/// 数值滚动：从 0 滚动到目标整数，结果卡统计用的活泼数字动效
private struct CountUpNumber: View {
    let value: Int
    let textStyle: Font.TextStyle
    let color: Color
    /// 可选固定字号；传 nil 时回退到 textStyle 对应字号
    var size: CGFloat? = nil
    @State private var shown: CGFloat = 0

    var body: some View {
        Text("\(Int(shown))")
            .font(size.map { .system(size: $0, weight: .bold) }
                   ?? .system(textStyle, design: .default, weight: .bold))
            .monospacedDigit()
            .foregroundStyle(color)
            .contentTransition(.numericText())
            .onAppear {
                shown = 0
                withAnimation(.spring(response: 0.9, dampingFraction: 0.82)) {
                    shown = CGFloat(value)
                }
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
    /// 是否启用内置渐变动画。总进度条由 AppState 插值器平滑驱动，应传 false；
    /// 单作业行级进度条仍靠步骤跳变，保留 true。
    var animated: Bool = true
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
        .animation(animated ? .easeOut(duration: 0.4) : nil, value: fraction)
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
    let theme: AppTheme

    var body: some View {
        VStack(spacing: HW_CARD_GAP) {
            ForEach(0..<4, id: \.self) { i in
                SkeletonCard(theme: theme)
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

/// 单张骨架占位卡：勾选框 + 两行标题条 + 状态条，带主题色流光扫过（与顶部加载条同语言）
private struct SkeletonCard: View {
    let theme: AppTheme

    var body: some View {
        HStack(spacing: HW_ROW_ICON_GAP) {
            RoundedRectangle(cornerRadius: 5)
                .fill(Color.primary.opacity(0.10))
                .frame(width: 17, height: 17)
            VStack(alignment: .leading, spacing: 9) {
                SkeletonBar(theme: theme, height: 12)
                SkeletonBar(theme: theme, height: 9)
                    .frame(width: 120)
            }
            Spacer(minLength: 8)
            SkeletonBar(theme: theme, height: 9)
                .frame(width: 56)
        }
        .padding(.horizontal, HW_CARD_H_PAD)
        .padding(.vertical, HW_CARD_V_PAD)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: HW_CARD_RADIUS, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: HW_CARD_RADIUS, style: .continuous)
                .strokeBorder(Color(nsColor: .separatorColor).opacity(0.4), lineWidth: 1)
        )
    }
}

/// 灰色底 + 主题色往复流光扫过的骨架条（洗白改为品牌色，与 LoadingTopStrip 一致）
private struct SkeletonBar: View {
    let theme: AppTheme
    let height: CGFloat
    @State private var sweep: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Capsule().fill(Color.primary.opacity(0.10))
                Capsule()
                    .fill(LinearGradient(colors: [.clear, theme.primary.opacity(0.30), .clear],
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

// MARK: - 课程骨架屏（刷新课程界面的年轻化占位）

/// 课程网格骨架屏：占位卡与真实课程卡同构（上封面 + 下两行标题），带主题色流光扫过。
private struct SkeletonCourseList: View {
    @State private var appeared = false
    let theme: AppTheme
    private let columns = [GridItem(.adaptive(minimum: 196, maximum: 320), spacing: 16)]
    // 官方封面宽高比约 240:130
    private let coverRatio: CGFloat = 240.0 / 130.0

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 14) {
                ForEach(0..<6, id: \.self) { i in
                    SkeletonCourseCard(theme: theme, coverRatio: coverRatio)
                        .transition(.asymmetric(
                            insertion: .opacity.combined(with: .scale(scale: 0.96)).combined(with: .move(edge: .bottom)),
                            removal: .opacity))
                        .animation(.spring(response: 0.5, dampingFraction: 0.72).delay(Double(i) * 0.06),
                                   value: appeared)
                }
            }
            .padding(20)
        }
        .onAppear { appeared = true }
    }
}

/// 单张课程骨架占位卡：上整宽封面块 + 右下两行标题条，复用 SkeletonBar 的流光语言。
private struct SkeletonCourseCard: View {
    let theme: AppTheme
    let coverRatio: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            GeometryReader { geo in
                SkeletonShimmer(theme: theme)
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }
            .frame(maxWidth: .infinity)
            .aspectRatio(coverRatio, contentMode: .fit)
            .clipped()

            VStack(alignment: .leading, spacing: 7) {
                SkeletonBar(theme: theme, height: 12)
                SkeletonBar(theme: theme, height: 9)
                    .frame(width: 90)
            }
            .padding(.horizontal, 3)
            .padding(.top, 10)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color(nsColor: .separatorColor).opacity(0.3), lineWidth: 1)
        )
    }
}

/// 整块流光底：灰色底 + 主题色条纹扫过，用于封面这类大面积占位。
private struct SkeletonShimmer: View {
    let theme: AppTheme
    @State private var sweep: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.primary.opacity(0.08)
                LinearGradient(colors: [.clear, theme.primary.opacity(0.18), .clear],
                               startPoint: .leading, endPoint: .trailing)
                    .frame(width: geo.size.width * 0.6)
                    .offset(x: sweep * geo.size.width * 1.3)
            }
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
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
/// `enabled` 为 false 时不做抬升/投影，避免禁用态仍“发光”。
struct HoverLift: ViewModifier {
    let shadowColor: Color
    var enabled: Bool = true
    @State private var hovering = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(enabled && hovering ? 1.04 : 1)
            .shadow(color: (enabled && hovering ? shadowColor : .clear).opacity(0.32), radius: 10, y: 4)
            .animation(.easeOut(duration: 0.15), value: hovering)
            .onHover { hovering = enabled && $0 }
    }
}

extension View {
    /// 统一给按钮加悬停「抬升 + 柔影」动效。
    func hoverLift(shadowColor: Color = .gray, enabled: Bool = true) -> some View {
        modifier(HoverLift(shadowColor: shadowColor, enabled: enabled))
    }
}

/// 主题色主按钮：平坦填充、圆角 8，悬停抬升、按下缩放。
/// 禁用态（`disabled == true`）自动置灰、去悬停、降不透明度，让用户明白此时不可点击。
/// 传 `gradient`（≥2 色）时用主题渐变填充（如「开始抓取」主 CTA），否则用纯色 theme.primary。
/// hover 视觉：悬停时亮化填充 + 中性色投影抬升，解决纯色填充上"同色系阴影不可见"的问题。
struct MinimalBrandButtonStyle: ButtonStyle {
    let theme: AppTheme
    var disabled: Bool = false
    var gradient: [Color]? = nil

    func makeBody(configuration: Configuration) -> some View {
        BrandButtonLabel(theme: theme, disabled: disabled, gradient: gradient,
                         isPressed: configuration.isPressed, label: configuration.label)
    }
}

/// 主题色主按钮的实际渲染：内建 `@State hovering`，据此做亮化 + 抬升 + 中性投影。
private struct BrandButtonLabel: View {
    let theme: AppTheme
    let disabled: Bool
    let gradient: [Color]?
    let isPressed: Bool
    let label: ButtonStyleConfiguration.Label
    @State private var hovering = false

    var body: some View {
        let active = !disabled
        let gradientColors = gradient ?? [theme.primary]
        label
            .foregroundStyle(active ? .white : .secondary)
            .padding(.horizontal, 20)
            .padding(.vertical, 9)
            .background(fillArea(active: active, gradientColors: gradientColors))
            .brightness(active ? (isPressed ? -0.06 : (hovering ? 0.10 : 0)) : 0)
            .scaleEffect(active ? (isPressed ? 0.97 : (hovering ? 1.04 : 1)) : 1)
            .opacity(active ? 1 : 0.65)
            .shadow(color: (active && hovering ? Color.black.opacity(0.22) : .clear),
                    radius: 10, y: 4)
            .animation(.easeOut(duration: 0.15), value: hovering)
            .animation(.easeOut(duration: 0.12), value: isPressed)
            .onHover { hovering = active && $0 }
    }

    @ViewBuilder
    private func fillArea(active: Bool, gradientColors: [Color]) -> some View {
        let shape = RoundedRectangle(cornerRadius: 8, style: .continuous)
        if !active {
            shape.fill(Color(nsColor: .separatorColor).opacity(0.28))
        } else if gradientColors.count > 1 {
            shape.fill(
                LinearGradient(colors: isPressed ? gradientColors.map { $0.opacity(0.85) } : gradientColors,
                               startPoint: .leading, endPoint: .trailing)
            )
        } else {
            shape.fill(isPressed ? theme.primary.opacity(0.85) : theme.primary)
        }
    }
}

extension ButtonStyle where Self == MinimalBrandButtonStyle {
    static func minimalBrand(theme: AppTheme, disabled: Bool = false, gradient: [Color]? = nil) -> MinimalBrandButtonStyle {
        .init(theme: theme, disabled: disabled, gradient: gradient)
    }
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

/// 空闲态引导的单个步骤卡（年轻化、主题色强调、轻投影）
private struct IdleStep: View {
    let number: String
    let icon: String
    let title: String
    let subtitle: String
    let theme: AppTheme
    @State private var lifted = false

    var body: some View {
        VStack(spacing: 9) {
            // 圆形步骤图标：主题色软填充 + 投影抬升
            ZStack {
                Circle()
                    .fill(theme.primary.opacity(0.12))
                Image(systemName: icon)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(theme.primary)
                Text(number)
                    .font(.system(size: 11, weight: .heavy))
                    .foregroundStyle(.white)
                    .frame(width: 19, height: 19)
                    .background(Circle().fill(theme.primary))
                    .offset(x: 24, y: -24)
            }
            .frame(width: 64, height: 64)
            Text(title)
                .font(.headline.weight(.semibold))
                .foregroundStyle(.primary)
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(width: 168)
        .padding(.vertical, 18)
        .padding(.horizontal, 10)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Color.primary.opacity(0.06), lineWidth: 1)
        )
        .shadow(color: theme.primary.opacity(lifted ? 0.12 : 0.04), radius: 8, y: 3)
        .scaleEffect(lifted ? 1.03 : 1)
        .animation(.easeOut(duration: 0.18), value: lifted)
        .onHover { lifted = $0 }
    }
}

// MARK: - 课程卡片（选课程主区域）

/// 按课程 id/url 稳定派生一个封面色相，保证同一课程每次都得到相同颜色。
private func courseTint(_ c: CourseItem) -> Color {
    let key = c.courseID.isEmpty ? c.url : c.courseID
    var hash: UInt64 = 5381
    for byte in key.utf8 {
        hash = (hash &* 33) &+ UInt64(byte)
    }
    let hue = Double(hash % 360) / 360.0
    return Color(hue: hue, saturation: 0.48, brightness: 0.88)
}

/// 单门课程卡片（贴近学习通官方样式）：上方全宽真实封面缩略图 + 下方标题（两行截断）+ 教师。
/// 选中态主题色描边 + 封面右上角对勾角标；悬停轻微抬升。
private struct CourseCard: View {
    @Environment(AppState.self) private var app
    let course: CourseItem
    let isSelected: Bool
    let onTap: () -> Void
    private var theme: AppTheme { app.theme }
    private var tint: Color { courseTint(course) }
    @State private var hovering = false
    // 点按反馈：短暂下压后回弹（scale 0.98）
    @State private var isSelectedTapped = false

    // 官方封面约 240×130（宽高比 ≈ 1.846，页面实际展示也是该比例）
    private let coverRatio: CGFloat = 240.0 / 130.0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            cover
                .overlay {
                    if course.ended {
                        // 已结束课程：深色遮罩 + 状态标签
                        ZStack {
                            Color.black.opacity(0.45)
                            VStack(spacing: 4) {
                                Image(systemName: "lock.fill")
                                    .font(.system(size: 14, weight: .semibold))
                                Text("课程已结束")
                                    .font(.caption.weight(.semibold))
                            }
                            .foregroundStyle(.white)
                        }
                        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                    }
                }
                .overlay(alignment: .topTrailing) {
                    if isSelected {
                        ZStack {
                            Circle()
                                .fill(Color(nsColor: .windowBackgroundColor))
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 20, weight: .semibold))
                                .foregroundStyle(theme.primary)
                        }
                        .frame(width: 26, height: 26)
                        .padding(7)
                        .transition(.asymmetric(
                            insertion: .scale(scale: 0.3).combined(with: .opacity),
                            removal: .opacity))
                    }
                }
            VStack(alignment: .leading, spacing: 4) {
                Text(course.title)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                Text(course.teacher.isEmpty ? "教师未知" : course.teacher)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 3)
            .padding(.top, 8)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        // 选中态：主题色柔和外发光雾环（内外对接渐变，随选中/悬停出现）
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(theme.primary.opacity(isSelected || hovering ? 0.28 : 0), lineWidth: 1.5)
                .padding(-2.5)
                .blur(radius: 4)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(
                    isSelected ? theme.primary.opacity(0.85)
                               : hovering ? theme.primary.opacity(0.55)
                                          : Color(nsColor: .separatorColor).opacity(0.35),
                    lineWidth: isSelected ? 1.5 : 1)
        )
        .contentShape(Rectangle())
        .scaleEffect(hovering ? 1.025 : (isSelectedTapped ? 0.98 : 1))
        .shadow(color: (isSelected || hovering ? theme.primary : .clear).opacity(isSelected ? 0.22 : 0.16), radius: 14, y: 5)
        .animation(.spring(response: 0.35, dampingFraction: 0.7), value: hovering)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: isSelected)
        .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isSelectedTapped)
        .onHover { hovering = $0 }
        .onTapGesture {
            onTap()
            // 点按反馈：轻微下压后回弹
            isSelectedTapped = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
                withAnimation { isSelectedTapped = false }
            }
        }
        .help(course.title)
    }

    /// 真实课程封面缩略图：全宽、按官方 240×130 比例，加载成功显示封面；无封面/失败用主题色渐变兜底。
    private var cover: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = w / coverRatio
            Group {
                if coverURL != nil {
                    AsyncImage(url: coverURL) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().scaledToFill()
                                .frame(width: w, height: h)
                        case .failure:
                            placeholder.frame(width: w, height: h)
                        default:
                            placeholder.opacity(0.7).frame(width: w, height: h)
                        }
                    }
                } else {
                    placeholder.frame(width: w, height: h)
                }
            }
            .scaleEffect(hovering ? 1.06 : 1)
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
        .frame(maxWidth: .infinity)
        .aspectRatio(coverRatio, contentMode: .fit)
        .clipped()
        .animation(.spring(response: 0.4, dampingFraction: 0.78), value: hovering)
    }

    private var coverURL: URL? {
        guard !course.cover.isEmpty else { return nil }
        return URL(string: course.cover)
    }

    private var placeholder: some View {
        ZStack {
            LinearGradient(colors: [tint, tint.opacity(0.55)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            Image(systemName: "book.closed.fill")
                .font(.system(size: 24, weight: .semibold))
                .foregroundStyle(.white.opacity(0.9))
        }
    }
}