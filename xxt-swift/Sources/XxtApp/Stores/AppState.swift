import Foundation
import SwiftUI
import AppKit
import UserNotifications

@Observable
final class AppState {
    // 引擎
    let engine = PythonEngine()
    var settings = EngineSettings()
    var isEngineBusy = false

    // 作业
    var homeworks: [HomeworkItem] = []
    var repairItems: [RepairItem] = []
    var progressItems: [ProgressItem] = []
    var selectedHomeworkIDs: Set<String> = []
    var repairSelection: Set<String> = []
    var logAutoScroll = true

    // 「选课程」流程：账号课程列表与当前选中课程
    var courses: [CourseItem] = []
    var selectedCourse: CourseItem?
    // 正在加载课程列表（用于展示「加载中」反馈，区别于作业加载）
    var isLoadingCourses = false
    // 应用启动时是否已触发过一次静默预加载课程（保证只自动加载一次）
    var didAutoPreloadCourses = false

    // 运行状态
    var isRunning = false
    // 本次运行已下发引擎的作业 ID 集合（初始 = 开始抓取时选中的集合；
    // 运行中「新增作业」会追加）。用于保证同一作业运行期只入队一次，且只允许新增、不允许移除。
    var runAddHomeworkIDs: Set<String> = []
    // 停止二次确认态：第一次点「停止」置为 true（按钮变「确认停止」），第二次点才真正停止
    var stopArmed = false
    // 确认态超时自动复位用的可取消任务（.now + 10s）
    private var stopResetWorkItem: DispatchWorkItem?
    private let stopConfirmTimeout: TimeInterval = 10
    // 是否已保存有效登录态（state.json），应用启动时由引擎查询初始化，
    // 用于设置界面在「登录学习通 / 退出登录」之间动态切换。
    var isLoggedIn = false
    var isLoggingIn = false
    var loginMessage = ""
    // 无头扫码登录用的二维码 PNG base64（登录成功/取消后清空）
    var loginQRImageB64 = ""
    // 用户点击「已完成登录」后、引擎验证登录态的阻塞期，用于展示“正在验证登录”反馈
    var isVerifyingLogin = false
    // 登录成功提示弹窗（引擎判定「扫码登录成功」后触发）
    var showLoginSuccess = false
    var loginSuccessMessage = "登录成功"
    // 课程 URL 为空时点击刷新的提示弹窗
    var showURLError = false
    var urlErrorMessage = "请先填写课程 URL"
    // 图片下载失败提醒（抓取完成后弹窗）
    var showImageFailAlert = false
    var imageFailMessage = "部分图片下载失败"
    private var pendingImageFailures = 0
    // 启动时网络代理检测（VPN/系统代理可能影响抓取稳定性，仅启动检查一次）
    var showProxyAlert = false
    var proxyMessage = ""
    var lastOutputDir = ""
    var courseName = ""

    // 抓取进度（来自引擎 progress 事件，作业级累计 1..total）
    var progressCurrent = 0
    var progressTotal = 0
    // 总进度联动值：由引擎的单作业 in_progress 进度实时映射（0~1）。
    // 存在时总进度条优先用它平滑前进，而非仅按作业跳格。
    var overallProgress: Double?
    // 总进度「显示层」值（0~1）：与目标 progressTarget 分离，由 60fps 插值器平滑逼近，
    // 避免引擎频繁上报导致 ProgressBar 的 animation 每次被中断、观感生硬。
    var displayProgress: Double = 0
    // 本次抓取的成功 / 失败作业计数，用于「结果卡」展示
    var runOkCount = 0
    var runFailCount = 0
    // 本次抓取图片下载失败计数，用于结果卡「图片下载失败 k 张」
    var runImageFailCount = 0
    // 本次抓取起止时刻，结果卡展示抓取耗时
    var runStartDate: Date?
    var runEndDate: Date?
    // 最近一次抓取是否已结束（用于在任务流主视图切换「结果卡」）
    var lastRunFinished = false
    // 本会话内已抓取成功的作业 id 集合：作业行首展示「已抓」印记，刷新列表后仍保留
    var completedHomeworkIds = Set<String>()
    // 本次会话是否真正发起了抓取（用于区分「done 来自 load_homeworks」还是来自 start）
    private var fetchStarted = false
    /// 当前生效主题（固定为「活力靛蓝」，不再提供切换入口）
    var theme: AppTheme { AppTheme.indigo }

    // 抓取完成提示偏好（纯 UI 侧，本地持久化，不同步 Python）
    var playSoundOnComplete: Bool
    var notifyOnComplete: Bool

    // 日志
    var logs: [LogLine] = []
    private var logSeq = 0

    /// 引擎工作/数据目录：引擎回报的相对路径基于它解析，不再写死开发者机器路径。
    static var defaultProjectDir: String { PythonEngine.workingDir }

    /// 由设置里的「外观」偏好推导出的界面配色，nil 表示跟随系统
    var preferredColorScheme: ColorScheme? {
        switch settings.appearance {
        case "light": return .light
        case "dark": return .dark
        default: return nil
        }
    }

    /// 将外观偏好一次性应用到全局窗口，避免用 `.preferredColorScheme` 修饰符逐渲染 re-apply。
    /// macOS 26(Liquid Glass) 下，`.preferredColorScheme` 会把外观反复套用到宿主视图，导致主界面
    /// 全部元素持续重绘闪烁；改为在「外观变化时」设一次 `NSApp.appearance` 即可稳定切换且不闪烁。
    func applyAppearance() {
        let appearance: NSAppearance?
        switch preferredColorScheme {
        case .light: appearance = NSAppearance(named: .aqua)
        case .dark:  appearance = NSAppearance(named: .darkAqua)
        default:     appearance = nil // 跟随系统
        }
        NSApplication.shared.appearance = appearance
    }

    /// 总进度「目标值」（0...1）：由引擎整体联动值覆盖，否则回退为作业级计数。
    private var progressTarget: Double {
        if let o = overallProgress {
            return min(max(o, 0), 1)
        }
        guard progressTotal > 0 else { return 0 }
        return Double(min(progressCurrent, progressTotal)) / Double(progressTotal)
    }

    /// 抓取进度分数（0...1），供进度条使用。
    /// 返回「显示层」displayProgress——由插值器以限速渐出逼近目标值，
    /// 因此总进度条在单作业进度变化时也会平滑、连贯地前进，而非瞬时跳变。
    var progressFraction: Double {
        min(max(displayProgress, 0), 1)
    }

    /// 抓取进度百分比（0...100）
    var progressPercent: Int {
        Int((progressFraction * 100).rounded())
    }

    // ---------- 总进度平滑插值器 ----------
    // CadenceLink 无法在 @Observable 直接持有，用 Timer 即可满足 60fps 展示需求。
    private var progressTicker: Timer?

    /// 启动 60fps 定时器，每帧把 displayProgress 向 progressTarget 平滑逼近一次。
    private func startProgressInterpolator() {
        guard progressTicker == nil else { return }
        let timer = Timer(timeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            self?.tickProgressInterpolator()
        }
        // 加入主运行循环通用模式，避免拖动/滚动时暂停导致的进度顿挫
        RunLoop.main.add(timer, forMode: .common)
        progressTicker = timer
    }

    /// 单次插值帧：渐出逼近——差距越大推进越快，越接近目标越平稳，且设置速率上限防跳变。
    private func tickProgressInterpolator() {
        let target = progressTarget
        var current = displayProgress
        if current >= target {
            // 到达或超过目标：直接锁定，避免抖动与反向
            current = target
        } else {
            // 指数渐出：差值按 ~12% 收敛，配合速率上限，视觉上平滑匀速地爬到目标
            let step = (target - current) * 0.12
            let maxStep = 0.02   // 单帧最多推进 2%，约 1.2%/帧 * 60 = 平滑且不跳跃
            current = current + min(step, maxStep)
            // 极接近目标时直接收敛到位，避免数值上永远差一丝
            if target - current < 0.0005 {
                current = target
            }
        }
        if abs(current - displayProgress) > 0.000001 {
            displayProgress = current
        }
    }

    /// 播放提示音的持久化 setter（随 didSet 写 UserDefaults）
    func setPlaySound(_ on: Bool) {
        playSoundOnComplete = on
        UserDefaults.standard.set(on, forKey: "playSoundOnComplete")
    }

    func setNotify(_ on: Bool) {
        notifyOnComplete = on
        UserDefaults.standard.set(on, forKey: "notifyOnComplete")
    }

    init() {
        playSoundOnComplete = UserDefaults.standard.object(forKey: "playSoundOnComplete") as? Bool ?? true
        notifyOnComplete = UserDefaults.standard.object(forKey: "notifyOnComplete") as? Bool ?? true
        engine.onEvent = { [weak self] event in
            self?.handle(event)
        }
        engine.onExit = { [weak self] in
            guard let self else { return }
            self.isEngineBusy = false
            self.isRunning = false
            self.stopArmed = false
            self.cancelStopArmReset()
            self.appendLog("引擎已退出", level: "error")
        }
        // 启动 60fps 插值器：让 displayProgress 持续向 progressTarget 平滑逼近
        startProgressInterpolator()
    }

    // MARK: - 生命周期

    func startEngine() {
        guard !engine.isRunning else { return }
        appendLog("正在启动 Python 引擎…", level: "info")
        engine.launch()
        // 引擎就绪后拉取一次 Python 侧设置（含 output_dir），
        // 否则 app.settings 停在默认空值，页脚会误显示“未设置输出目录”。
        refreshSettings()
        // 启动时检查是否已保存登录态，供设置界面切换「登录/退出」按钮
        refreshLoginStatus()
        // 启动即检测网络代理：VPN/系统代理可能影响抓取稳定性，命中则弹窗提示
        checkProxyAtStartup()
    }

    /// 启动时网络代理检测：系统代理或环境变量命中任一即弹窗提示。
    /// 只检测、不阻断，便于用户知晓 VPN 可能影响抓取稳定性。
    func checkProxyAtStartup() {
        guard let desc = proxyDescription else { return }
        proxyMessage = desc
        appendLog("检测到网络代理（可能影响抓取稳定性）：\(desc)", level: "warn")
        showProxyAlert = true
    }

    /// 汇总当前启用的网络代理（系统代理 + 环境变量），无则返回 nil。
    private var proxyDescription: String? {
        // 1) 环境变量
        var envHits: [String] = []
        let env = ProcessInfo.processInfo.environment
        for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"] {
            if let v = env[key], !v.isEmpty { envHits.append("\(key)=\(v)") }
        }
        // 2) 系统代理（scutil --proxy）
        var systemHits: [String] = []
        if let sys = systemProxyState {
            for (key, label) in [("HTTPEnable", "HTTP"), ("HTTPSEnable", "HTTPS"),
                                 ("SOCKSEnable", "SOCKS"), ("ProxyAutoConfigEnable", "自动配置 PAC")] {
                if sys[key] == "1" { systemHits.append(label) }
            }
        }
        if systemHits.isEmpty && envHits.isEmpty { return nil }
        var parts: [String] = systemHits
        if !envHits.isEmpty { parts.append("环境变量 " + envHits.joined(separator: ", ")) }
        return parts.joined(separator: "；")
    }

    /// 执行 `scutil --proxy` 读取系统网络代理状态，解析为 key → value。
    private var systemProxyState: [String: String]? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/sbin/scutil")
        p.arguments = ["--proxy"]
        let out = Pipe()
        p.standardOutput = out
        do { try p.run(); p.waitUntilExit() } catch { return nil }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        let txt = String(data: data, encoding: .utf8) ?? ""
        var result: [String: String] = [:]
        let pattern = #/\s*(\w+)\s*:\s*(.+)/#
        for line in txt.split(separator: "\n") {
            guard let m = line.firstMatch(of: pattern) else { continue }
            let key = String(m.1)
            let val = String(m.2).replacingOccurrences(of: "\"", with: "").trimmingCharacters(in: .whitespaces)
            result[key] = val
        }
        return result
    }

    /// 向引擎查询当前是否已保存有效登录态，并更新 isLoggedIn。
    func refreshLoginStatus() {
        engine.loginStatus { [weak self] loggedIn in
            DispatchQueue.main.async {
                guard let self else { return }
                self.isLoggedIn = loggedIn
                // 启动即静默预加载课程：已登录时在教程卡片期间就把课程列表拉好，
                // 用户点「开始」时无需等待。仅执行一次。
                if loggedIn {
                    self.preloadCoursesIfLoggedIn()
                }
            }
        }
    }

    /// 启动后台静默预加载课程列表（已登录且首次才执行）。
    /// 若引擎此刻仍忙碌（例如正在拉取设置），稍作延迟重试，避免本次静默加载被吞掉。
    func preloadCoursesIfLoggedIn(retriesRemaining: Int = 4) {
        guard !didAutoPreloadCourses else { return }
        guard isLoggedIn else { return }
        if isEngineBusy {
            guard retriesRemaining > 0 else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
                self?.preloadCoursesIfLoggedIn(retriesRemaining: retriesRemaining - 1)
            }
            return
        }
        didAutoPreloadCourses = true
        appendLog("已登录，后台静默加载课程列表…", level: "info")
        engine.listCourses()
        courses.removeAll()
        selectedCourse = nil
        isLoadingCourses = true
        isEngineBusy = true
    }

    // MARK: - 事件处理

    private func handle(_ event: EngineEvent) {
        switch event.kind {
        case .log:
            appendLog(event.value.message ?? "", level: event.value.level ?? "info")
        case .progress:
            if let total = event.value.total, total > 0, let current = event.value.current {
                progressCurrent = current
                progressTotal = total
                courseName = event.value.title ?? ""
                // 作业完成计格时，回退为按作业计数（让下一个 in_progress 再接管平滑联动）
                overallProgress = nil
            }
        case .loginPrompt:
            isLoggingIn = true
            isVerifyingLogin = false
            loginMessage = event.value.message ?? "请在浏览器中完成登录"
            loginQRImageB64 = ""
            appendLog("等待登录：\(loginMessage)", level: "info")
        case .loginQr:
            isLoggingIn = true
            isVerifyingLogin = false
            loginMessage = event.value.message ?? "请用学习通App扫码登录"
            loginQRImageB64 = event.value.imageB64 ?? ""
        case .loginSuccess:
            // 引擎判定登录成功：立即退出登录/验证界面并弹出登录成功提示
            isLoggingIn = false
            isVerifyingLogin = false
            isLoggedIn = true
            loginQRImageB64 = ""
            loginSuccessMessage = event.value.message ?? "扫码登录成功，已保存登录状态。"
            if !showLoginSuccess {
                showLoginSuccess = true
            }
            appendLog("登录成功", level: "success")
            // 登录成功后同样在后台静默加载课程列表，避免二次等待
            preloadCoursesIfLoggedIn()
        case .courseList:
            isEngineBusy = false
            isLoadingCourses = false
            courses = event.value.courses ?? []
            appendLog("已加载 \(courses.count) 门课程", level: "success")
        case .homeworkList:
            isEngineBusy = false
            homeworks = event.value.items ?? []
            appendLog("已加载 \(homeworks.count) 个作业", level: "success")
        case .homeworkPage:
            // 翻页过程中的即时增量：每收到一页新作业就追加进列表，由主视图伴随弹入动效展示
            if let newItems = event.value.items, !newItems.isEmpty {
                homeworks.append(contentsOf: newItems)
            }
        case .imageFail:
            pendingImageFailures += event.value.failed ?? 1
            runImageFailCount = pendingImageFailures
        case .done:
            isEngineBusy = false
            isLoadingCourses = false
            isRunning = false
            stopArmed = false
            cancelStopArmReset()
            isLoggingIn = false
            isVerifyingLogin = false
            loginQRImageB64 = ""
            // 抓取完成后若存在图片下载失败，弹窗提醒并在展示后清零
            if (event.value.success ?? true) && pendingImageFailures > 0 {
                imageFailMessage = "本次抓取有 \(pendingImageFailures) 张图片下载失败，请检查网络连接后重试。"
                showImageFailAlert = true
            }
            pendingImageFailures = 0
            let msg = event.value.message ?? "完成"
            let success = event.value.success ?? true
            if let dir = event.value.outputDir, !dir.isEmpty {
                lastOutputDir = dir
            }
            // 结束标记：仅当本次确实发起了抓取时才切换「结果卡」并触发完成通知；
            // load_homeworks 也会触发 done，但不应点亮结果卡、也不应发完成通知。
            if fetchStarted {
                lastRunFinished = true
                fetchStarted = false
                runEndDate = Date()
                if success {
                    completionReminder()
                }
            }
            // 进度归零，避免进度条停留在最后一个位置
            progressCurrent = 0
            progressTotal = 0
            overallProgress = nil
            displayProgress = 0
            appendLog(msg, level: success ? "success" : "error")
            refreshProgressIfNeeded()
        case .status:
            handleStatusEvent(event.value)
        case .error:
            isEngineBusy = false
            isLoadingCourses = false
            appendLog(event.value.message ?? "错误", level: "error")
        }
    }

    /// 抓取成功后的完成提示：按偏好播放系统提示音 + 发送系统通知。
    /// 在调用方（主线程事件回调）执行。
    private func completionReminder() {
        if playSoundOnComplete, let sound = NSSound(named: "Glass") {
            sound.play()
        }
        guard notifyOnComplete else { return }
        let center = UNUserNotificationCenter.current()
        // 仅当用户已授权（authorized/临时的 provisional）且开启横幅时才真正发送；
        // 未授权、被拒绝或只在通知中心展示时静默跳过，避免无意义 add 失败。
        center.getNotificationSettings { settings in
            let authorized = settings.authorizationStatus == .authorized
                || settings.authorizationStatus == .provisional
            guard authorized, settings.alertSetting == .enabled else { return }
            let content = UNMutableNotificationContent()
            content.title = "学习通作业爬取工具"
            // 用本轮实际处理结果计数（含运行中新增作业），而非一开始的勾选数，避免少报
            content.body = "抓取完成：已处理 \(self.runOkCount + self.runFailCount) 个作业"
            content.sound = .default
            let req = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: content,
                trigger: nil
            )
            center.add(req)
        }
    }

    /// 实时作业状态跟踪：更新侧栏对应作业的状态徽标，并追加一条日志
    private func handleStatusEvent(_ value: EngineEventValue) {
        let title = value.title ?? ""
        let status = value.status ?? ""
        let url = value.url

        // 依据 url（优先）或标题匹配列表中的作业并就地更新
        if let idx = homeworks.firstIndex(where: { hw in
            (url != nil && hw.url == url) || (url == nil && !title.isEmpty && hw.title == title)
        }) {
            homeworks[idx].status = status
            // 单作业进度：completed 置满，其余用引擎上报的 0~1 进度（未上报保持原值）
            if status == "completed" {
                homeworks[idx].progress = 1.0
                completedHomeworkIds.insert(homeworks[idx].id)
            } else if let p = value.progress {
                homeworks[idx].progress = p
            }
        }

        // 总进度联动：in_progress 且引擎附带了整体进度时，平滑驱动总进度条
        if status == "in_progress", let overall = value.overall {
            overallProgress = min(max(overall, 0), 1)
        }

        let level = status == "completed" ? "success" : (status == "failed" ? "error" : "info")
        appendLog("\(status == "completed" ? "✓" : "✗") \(title) — \(status)", level: level)
        // 累计本次抓取的成功 / 失败计数，供「结果卡」展示
        switch status {
        case "completed": runOkCount += 1
        case "failed": runFailCount += 1
        default: break
        }
    }

    private func refreshProgressIfNeeded() {
        engine.send("list_progress") { [weak self] reply in
            guard let self, reply.ok, let items = reply.result?["items"] as? [[String: Any]] else { return }
            self.progressItems = items.compactMap { d -> ProgressItem? in
                guard let data = try? JSONSerialization.data(withJSONObject: d) else { return nil }
                return try? JSONDecoder().decode(ProgressItem.self, from: data)
            }
        }
    }

    // MARK: - 命令

    func refreshSettings() {
        engine.send("get_settings") { [weak self] reply in
            guard let self, reply.ok, let r = reply.result else { return }
            self.settings = decodeSettings(from: r)
        }
    }

    func saveSettings() {
        var params: [String: Any] = [:]
        if let data = try? JSONEncoder().encode(settings),
           let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            params = d
        }
        isEngineBusy = true
        engine.send("set_settings", params: ["settings": params]) { [weak self] reply in
            guard let self else { return }
            self.isEngineBusy = false
            if reply.ok, let r = reply.result {
                self.settings = decodeSettings(from: r)
                self.appendLog("设置已保存", level: "success")
            } else {
                self.appendLog(reply.error ?? "保存设置失败", level: "error")
            }
        }
    }

    /// 「选课程」：请求引擎从个人空间列取账号课程列表。
    /// 先复位所选课程与作业，保持状态干净；结果通过 courseList 事件回传后填充 courses。
    func loadCourses() {
        guard !isEngineBusy else {
            appendLog("请等待当前任务完成后再选择课程", level: "warn")
            return
        }
        if !isLoggedIn {
            // 未登录时先引导扫码；扫码成功事件会触发 loginSuccess 复位，
            // 用户可再次点击「选择课程」加载列表。
            appendLog("请先扫码登录学习通，再选择课程", level: "warn")
            startLogin()
            return
        }
        lastRunFinished = false
        courses.removeAll()
        selectedCourse = nil
        isLoadingCourses = true
        isEngineBusy = true
        appendLog("正在加载课程列表…", level: "info")
        engine.listCourses()
    }

    /// 选定一门课程：记录它，并用它的课程入口 URL 填充 courseURL，
    /// 供后续「加载作业列表」复用（engine 会自动跳到带 enc/t 的课程页）。
    func selectCourse(_ course: CourseItem) {
        selectedCourse = course
        settings.courseURL = course.url
        appendLog("已选择课程：\(course.title)", level: "success")
    }

    func loadHomeworks() {
        let trimmed = settings.courseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            urlErrorMessage = "请先选择课程或填写课程 URL，再点击加载作业列表。"
            showURLError = true
            appendLog("请先选择课程或填写课程 URL", level: "warn")
            return
        }
        // 开始新一轮“加载作业”，复位上轮结束标记与结果计数，
        // 避免刷新时主视图仍停留在「抓取完成」结果卡。
        lastRunFinished = false
        runOkCount = 0
        runFailCount = 0
        runImageFailCount = 0
        overallProgress = nil
        displayProgress = 0
        isEngineBusy = true
        homeworks.removeAll()
        completedHomeworkIds.removeAll()
        appendLog("正在加载作业列表…", level: "info")
        engine.send("load_homeworks", params: ["url": settings.courseURL])
    }

    func startSelected() {
        // 列表仍在加载/引擎忙碌时禁止启动，避免与加载完成的尾部 done 事件争夺 fetchStarted，
        // 从而误亮「抓取完成」结果卡。
        guard !isEngineBusy else {
            appendLog("请等待作业列表加载完成后再抓取", level: "warn")
            return
        }
        guard !selectedHomeworkIDs.isEmpty else {
            appendLog("请先勾选要抓取的作业", level: "warn")
            return
        }
        // 新一轮抓取：清零上轮结果计数并复位结束标记，记录起始时刻以统计耗时
        runOkCount = 0
        runFailCount = 0
        runImageFailCount = 0
        lastRunFinished = false
        runStartDate = Date()
        runEndDate = nil
        fetchStarted = true
        isEngineBusy = true
        isRunning = true
        stopArmed = false
        cancelStopArmReset()
        // 把本次选中的作业重置为「处理中」：让它们干净地进入本轮抓取列表，
        // 避免沿用上一轮遗留的「完成/失败」徽标与进度，直到本轮 status 事件逐个接管。
        for i in homeworks.indices where selectedHomeworkIDs.contains(homeworks[i].id) {
            homeworks[i].status = "processing"
            homeworks[i].progress = 0
        }
        runAddHomeworkIDs = selectedHomeworkIDs
        appendLog("开始抓取 \(selectedHomeworkIDs.count) 个作业…", level: "info")
        engine.send("start", params: ["homework_ids": Array(selectedHomeworkIDs)])

        // PDF 依赖预检：开启「保存后自动导出 PDF」但本机无 Word/LibreOffice 时，
        // 提前弹窗提示（仅提示，不强制关闭设置或阻断抓取）。
        if settings.autoExportPDF {
            engine.send("check_pdf_env", params: [:]) { [weak self] reply in
                guard let self else { return }
                DispatchQueue.main.async {
                    let available = (reply.result?["available"] as? NSNumber)?.boolValue ?? true
                    guard !available else { return }
                    let reason = (reply.result?["reason"] as? String) ?? "未检测到 PDF 转换环境"
                    self.appendLog("PDF 导出环境检测：\(reason)，将跳过自动导出 PDF", level: "warn")
                    self.presentPdfEnvMissingAlert(reason)
                }
            }
        }
    }

    /// 抓取进行中新增未抓取作业：下发引擎动态队列并入队，同时更新本地选择与行状态。
    /// 仅接受「本轮尚未下发、未在处理」的新作业；已选/已入队的会被过滤（只允许新增，不允许移除）。
    func addRunningHomeworks(_ ids: [String]) {
        guard isRunning else { return }
        let fresh = ids.filter { !selectedHomeworkIDs.contains($0) && !runAddHomeworkIDs.contains($0) }
        guard !fresh.isEmpty else { return }
        let newSet = Set(fresh)
        selectedHomeworkIDs.formUnion(newSet)
        runAddHomeworkIDs.formUnion(newSet)
        // 让新加入的作业置为「处理中」，直到引擎 status 事件逐个接管，避免「看似已选却从未处理」
        for i in homeworks.indices where newSet.contains(homeworks[i].id) {
            homeworks[i].status = "processing"
            homeworks[i].progress = 0
        }
        appendLog("运行中加入 \(fresh.count) 个新作业进抓取队列…", level: "info")
        engine.send("add_homeworks", params: ["homework_ids": fresh])
    }

    /// 缺少 PDF 转换环境时的模态提示（仅告知，不强制用户安装）。
    func presentPdfEnvMissingAlert(_ reason: String) {
        let alert = NSAlert()
        alert.messageText = "无法自动导出 PDF"
        alert.informativeText = "\(reason)。\n\n抓取仍会正常完成并保存为 Word，但「保存后自动导出 PDF」将被跳过。\n\n可安装 Microsoft Word 或 LibreOffice 后重新导出。"
        alert.alertStyle = .warning
        alert.addButton(withTitle: "知道了")
        DispatchQueue.main.async { alert.runModal() }
    }

    func stopTask() {
        engine.send("stop")
        appendLog("请求停止…", level: "warn")
    }

    /// 两个停止入口点击逻辑：第一次点击仅进入确认态（按钮变「确认停止」），
    /// 第二次点击才真正发送停止指令，防止误触「停止」导致已抓取进度被中断。
    /// 不使用系统确认框，纯由按钮文案/状态反馈，点击即时可见。
    func stopAction() {
        if stopArmed {
            cancelStopArmReset()
            stopArmed = false
            stopTask()
        } else {
            stopArmed = true
            appendLog("再次点击「确认停止」以停止当前任务。", level: "warn")
            scheduleStopArmReset()
        }
    }

    /// 确认态超时自动复位：10 秒内未点击「确认停止」则恢复为「停止」。
    private func scheduleStopArmReset() {
        cancelStopArmReset()
        let workItem = DispatchWorkItem { [weak self] in
            guard let self, self.stopArmed else { return }
            self.stopArmed = false
            self.appendLog("未在 10 秒内确认，已自动恢复为「停止」。如需停止请再次点击。", level: "debug")
        }
        stopResetWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + stopConfirmTimeout, execute: workItem)
    }

    private func cancelStopArmReset() {
        stopResetWorkItem?.cancel()
        stopResetWorkItem = nil
    }

    /// 本次抓取耗时（结果卡展示）；未完成或异常时返回空
    var runDurationText: String {
        guard let s = runStartDate, let e = runEndDate else { return "" }
        let d = max(0, e.timeIntervalSince(s))
        if d < 60 {
            return String(format: "%.1f 秒", d)
        }
        return "\(Int(d) / 60) 分 \(Int(d) % 60) 秒"
    }

    /// 返回作业选择页面（继续抓取）：仅隐藏结果卡，保留已加载的作业与勾选。
    func backToSelection() {
        lastRunFinished = false
    }

    /// 返回主菜单：隐藏结果卡、清空 URL/课程选中与作业列表，回到初始空闲状态，便于抓取其他课程。
    func backToMainMenu() {
        lastRunFinished = false
        settings.courseURL = ""
        selectedCourse = nil
        homeworks.removeAll()
        selectedHomeworkIDs.removeAll()
        runOkCount = 0
        runFailCount = 0
        runImageFailCount = 0
        runStartDate = nil
        runEndDate = nil
    }

    func loginDone() {
        // 进入验证态：引擎后台校验登录态（可能需等待页面跳转/刷新），
        // 期间展示“正在验证登录”反馈，避免用户误以为程序卡住。
        isVerifyingLogin = true
        appendLog("正在验证登录…", level: "info")
        engine.send("login_done")
    }

    /// 取消登录：退出登录/验证界面，并让引擎终止当前登录及关联的抓取任务。
    func cancelLogin() {
        isLoggingIn = false
        isVerifyingLogin = false
        loginQRImageB64 = ""
        appendLog("已取消登录，任务已终止", level: "warn")
        engine.loginCancel()
    }

    /// 独立发起扫码登录（设置中「登录学习通」入口）。引擎会打开登录页，
    /// 通过 loginPrompt/loginQr 事件驱动登录界面；登录成功后触发 loginSuccess。
    /// 已在登录中时不重复触发，避免叠出多个扫码弹窗。
    func startLogin() {
        guard !isLoggingIn else {
            appendLog("已在登录中，请勿重复操作", level: "warn")
            return
        }
        appendLog("发起登录学习通…", level: "info")
        engine.startLogin()
    }

    /// 退出登录：调用引擎清除本地登录状态文件（含 state.json）并关闭浏览器会话。
    func logout() {
        appendLog("正在退出登录并清除本地登录状态…", level: "info")
        engine.logout { [weak self] reply in
            guard let self else { return }
            if reply.ok {
                // 清除登录中的 UI 状态，回到未登录展示
                self.isLoggedIn = false
                self.isLoggingIn = false
                self.isVerifyingLogin = false
                self.loginQRImageB64 = ""
                self.appendLog("已退出登录", level: "success")
            } else {
                self.appendLog(reply.error ?? "退出登录失败", level: "error")
            }
        }
        isLoggingIn = false
        isVerifyingLogin = false
        loginQRImageB64 = ""
    }

    func collectRepairItems() {
        engine.send("collect_repair_items") { [weak self] reply in
            guard let self, reply.ok else { return }
            guard let raw = reply.result?["repair_items"] as? [[String: Any]] else { return }
            self.repairItems = raw.compactMap { d -> RepairItem? in
                guard let data = try? JSONSerialization.data(withJSONObject: d) else { return nil }
                return try? JSONDecoder().decode(RepairItem.self, from: data)
            }
            self.appendLog("发现 \(self.repairItems.count) 个待修复作业", level: "info")
        }
    }

    func repairSelected(_ paths: [String]) {
        guard !paths.isEmpty else {
            appendLog("没有可修复的作业", level: "warn")
            return
        }
        isEngineBusy = true
        isRunning = true
        engine.send("repair_selected", params: ["paths": paths])
    }

    func openLastOutput() {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let fallback = "\(home)/Desktop/out"
        let rel = lastOutputDir.isEmpty ? (settings.outputDir.isEmpty ? fallback : settings.outputDir) : lastOutputDir
        let dir = rel.hasPrefix("/") ? rel : "\(fallback)"
        NSWorkspace.shared.open(URL(fileURLWithPath: dir))
    }

    // MARK: - 存储空间

    /// 输出目录存储占用统计（按类型分类）。
    struct StorageUsage {
        var totalBytes: Int64 = 0
        var wordBytes: Int64 = 0
        var imageBytes: Int64 = 0
        var pdfBytes: Int64 = 0
        var otherBytes: Int64 = 0
        /// 已生成的课程输出子目录数（不含 debug）
        var runCount: Int = 0
        var isEmpty: Bool { totalBytes <= 0 }
    }

    /// 计入「图片」类型的文件扩展名
    private static let imageExtensions: Set<String> = [
        "png", "jpg", "jpeg", "gif", "webp", "heic", "bmp", "tiff", "tif"
    ]

    /// 当前输出目录根路径（兜底 ~/Desktop/out）
    func outputRootPath() -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let dir = settings.outputDir
        if !dir.isEmpty && dir.hasPrefix("/") { return dir }
        return "\(home)/Desktop/out"
    }

    /// 字节数格式化（B / KB / MB / GB）
    func formatBytes(_ bytes: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }

    /// 统计输出目录存储占用，按 Word / 图片 / PDF / 其他分类。目录不存在或不可访问时返回空统计。
    func storageUsage() -> StorageUsage {
        var usage = StorageUsage()
        let fm = FileManager.default
        let root = outputRootPath()
        var isDir: ObjCBool = false
        guard fm.fileExists(atPath: root, isDirectory: &isDir), isDir.boolValue else { return usage }

        // 顶层课程输出子目录数（不含 debug 与隐藏文件）
        if let entries = try? fm.contentsOfDirectory(atPath: root) {
            usage.runCount = entries.filter { name in
                guard !name.hasPrefix(".") else { return false }
                guard name != "debug" else { return false }
                var d: ObjCBool = false
                return fm.fileExists(atPath: root + "/" + name, isDirectory: &d) && d.boolValue
            }.count
        }

        let keys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey]
        guard let en = fm.enumerator(at: URL(fileURLWithPath: root),
                                     includingPropertiesForKeys: keys,
                                     options: [.skipsHiddenFiles, .skipsPackageDescendants]) else { return usage }
        var total: Int64 = 0
        for case let url as URL in en {
            guard let values = try? url.resourceValues(forKeys: Set(keys)),
                  let isRegular = values.isRegularFile, isRegular,
                  let size = values.fileSize else { continue }
            let bytes = Int64(size)
            total += bytes
            let ext = url.pathExtension.lowercased()
            if ext == "docx" {
                usage.wordBytes += bytes
            } else if ext == "pdf" {
                usage.pdfBytes += bytes
            } else if Self.imageExtensions.contains(ext) {
                usage.imageBytes += bytes
            } else {
                usage.otherBytes += bytes
            }
        }
        usage.totalBytes = total
        return usage
    }

    /// 递归统计某目录总字节数。
    private func directoryBytes(at path: String) -> Int64 {
        let fm = FileManager.default
        let keys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey]
        guard let en = fm.enumerator(at: URL(fileURLWithPath: path),
                                     includingPropertiesForKeys: keys,
                                     options: [.skipsHiddenFiles, .skipsPackageDescendants]) else { return 0 }
        var total: Int64 = 0
        for case let url as URL in en {
            guard let values = try? url.resourceValues(forKeys: Set(keys)),
                  let isRegular = values.isRegularFile, isRegular,
                  let size = values.fileSize else { continue }
            total += Int64(size)
        }
        return total
    }

    /// 清理输出目录下的全部课程输出子目录与 debug 目录（保留输出根目录本身）。
    /// 返回被释放的字节数（>0 表示实际清理了内容）。
    @discardableResult
    func cleanupOutputFolders() -> Int64 {
        let fm = FileManager.default
        let root = outputRootPath()
        guard let entries = try? fm.contentsOfDirectory(atPath: root) else { return 0 }
        var freed: Int64 = 0
        for name in entries {
            guard !name.hasPrefix("."), name != ".DS_Store" else { continue }
            let path = root + "/" + name
            var isDir: ObjCBool = false
            guard fm.fileExists(atPath: path, isDirectory: &isDir), isDir.boolValue else { continue }
            freed += directoryBytes(at: path)
            do {
                try fm.removeItem(atPath: path)
            } catch {
                appendLog("清理失败：\(name) — \(error.localizedDescription)", level: "error")
            }
        }
        if freed > 0 {
            appendLog("已清理输出目录，释放 \(formatBytes(freed))", level: "success")
        } else {
            appendLog("输出目录已无可清理内容", level: "info")
        }
        return freed
    }

    func clearLogs() {
        logs.removeAll()
    }

    /// 打开内置帮助文档（HTML，用系统默认浏览器打开，不依赖 Xcode）。
    func openHelpDocument() {
        guard let url = Bundle.main.url(forResource: "Help", withExtension: "html") else {
            appendLog("找不到内置帮助文档 Help.html", level: "warn")
            return
        }
        NSWorkspace.shared.open(url)
    }

    func refreshHistory() {
        refreshProgressIfNeeded()
    }

    /// 清空「历史」界面的全部进度记录。
    func clearHistory() {
        engine.send("clear_progress") { [weak self] reply in
            guard let self else { return }
            if reply.ok {
                self.progressItems.removeAll()
                self.appendLog("已清空历史记录", level: "info")
            } else {
                self.appendLog(reply.error ?? "清空历史失败", level: "error")
            }
        }
    }

    // MARK: - 日志

    func appendLog(_ message: String, level: String = "info") {
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        // 去重：同一条消息连续出现两次（例如 print 与 LOGGER 双通道各来一次）时只展示一条
        if logs.last?.message == trimmed && logs.last?.level == level { return }
        logSeq += 1
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        logs.append(LogLine(id: logSeq, time: formatter.string(from: Date()), level: level, message: trimmed))
        if logs.count > 2000 {
            logs.removeFirst(logs.count - 2000)
        }
    }

    /// 一键复制全部运行日志到剪贴板（含时间与级别）。
    func copyLogsToClipboard() {
        let text = logs.map { line in
            "[\(line.time)] [\(line.level)] \(line.message)"
        }.joined(separator: "\n")
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        let ok = pasteboard.setString(text, forType: .string)
        appendLog(ok ? "已复制全部日志到剪贴板（\(logs.count) 条）" : "复制日志失败", level: ok ? "success" : "error")
    }

    /// 仅复制报错（error 级）日志到剪贴板，便于排查错误无需夹杂正常日志。
    func copyErrorLogsToClipboard() {
        let errs = logs.filter { $0.level == "error" }
        let text = errs.map { line in
            "[\(line.time)] [\(line.level)] \(line.message)"
        }.joined(separator: "\n")
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        let ok = pasteboard.setString(text, forType: .string)
        appendLog(ok ? "已复制报错日志到剪贴板（\(errs.count) 条）" : "复制报错日志失败", level: ok ? "success" : "error")
    }

    private func decodeSettings(from dict: [String: Any]) -> EngineSettings {
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return settings }
        let s = (try? JSONDecoder().decode(EngineSettings.self, from: data)) ?? settings
        return s
    }
}