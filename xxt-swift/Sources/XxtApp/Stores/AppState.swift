import Foundation
import SwiftUI
import AppKit
import UserNotifications

/// v2.0 界面模式：焕新界面 / 经典界面（老 UI）
enum AppUIMode: String, CaseIterable, Identifiable {
    case huanxin = "焕新界面"
    case classic = "经典界面"
    var id: String { rawValue }
}

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

    // 运行状态
    var isRunning = false
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
    var lastOutputDir = ""
    var courseName = ""

    // 抓取进度（来自引擎 progress 事件，作业级累计 1..total）
    var progressCurrent = 0
    var progressTotal = 0
    // 本次抓取的成功 / 失败作业计数，用于「结果卡」展示
    var runOkCount = 0
    var runFailCount = 0
    // 本次抓取图片下载失败计数，用于结果卡「图片下载失败 k 张」
    var runImageFailCount = 0
    // 最近一次抓取是否已结束（用于在任务流主视图切换「结果卡」）
    var lastRunFinished = false
    // 本次会话是否真正发起了抓取（用于区分「done 来自 load_homeworks」还是来自 start）
    private var fetchStarted = false
    // 主题 ID（本地持久化，仅预设主题，用户不可自由调色）
    var themeID: String {
        didSet { UserDefaults.standard.set(themeID, forKey: "themeID") }
    }
    /// 当前生效主题
    var theme: AppTheme { AppTheme.find(themeID) }

    // v2.0 界面模式（焕新 / 经典），本地持久化
    var uiMode: AppUIMode {
        didSet { UserDefaults.standard.set(uiMode.rawValue, forKey: "uiMode") }
    }

    // 抓取完成提示偏好（纯 UI 侧，本地持久化，不同步 Python）
    var playSoundOnComplete: Bool
    var notifyOnComplete: Bool

    // 日志
    var logs: [LogLine] = []
    private var logSeq = 0

    static let defaultProjectDir = "/Users/pengyufeng/Documents/xxt"

    /// 由设置里的「外观」偏好推导出的界面配色，nil 表示跟随系统
    var preferredColorScheme: ColorScheme? {
        switch settings.appearance {
        case "light": return .light
        case "dark": return .dark
        default: return nil
        }
    }

    /// 抓取进度分数（0...1），供进度条使用
    var progressFraction: Double {
        guard progressTotal > 0 else { return 0 }
        return Double(min(progressCurrent, progressTotal)) / Double(progressTotal)
    }

    /// 抓取进度百分比（0...100）
    var progressPercent: Int {
        Int((progressFraction * 100).rounded())
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
        themeID = UserDefaults.standard.string(forKey: "themeID") ?? "indigo"
        uiMode = AppUIMode(rawValue: UserDefaults.standard.string(forKey: "uiMode") ?? "") ?? .huanxin
        playSoundOnComplete = UserDefaults.standard.object(forKey: "playSoundOnComplete") as? Bool ?? true
        notifyOnComplete = UserDefaults.standard.object(forKey: "notifyOnComplete") as? Bool ?? true
        engine.onEvent = { [weak self] event in
            self?.handle(event)
        }
        engine.onExit = { [weak self] in
            guard let self else { return }
            self.isEngineBusy = false
            self.isRunning = false
            self.appendLog("引擎已退出", level: "error")
        }
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
    }

    /// 向引擎查询当前是否已保存有效登录态，并更新 isLoggedIn。
    func refreshLoginStatus() {
        engine.loginStatus { [weak self] loggedIn in
            DispatchQueue.main.async {
                self?.isLoggedIn = loggedIn
            }
        }
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
            isRunning = false
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
            // 结束标记：仅当本次确实发起了抓取时才切换「结果卡」；
            // load_homeworks 也会触发 done，但不应点亮结果卡。
            if fetchStarted {
                lastRunFinished = true
                fetchStarted = false
            }
            // 进度归零，避免进度条停留在最后一个位置
            progressCurrent = 0
            progressTotal = 0
            appendLog(msg, level: success ? "success" : "error")
            if success {
                completionReminder()
            }
            refreshProgressIfNeeded()
        case .status:
            handleStatusEvent(event.value)
        case .error:
            isEngineBusy = false
            appendLog(event.value.message ?? "错误", level: "error")
        }
    }

    /// 抓取成功后的完成提示：按偏好播放系统提示音 + 发送系统通知。
    /// 在调用方（主线程事件回调）执行。
    private func completionReminder() {
        if playSoundOnComplete, let sound = NSSound(named: "Glass") {
            sound.play()
        }
        if notifyOnComplete {
            let center = UNUserNotificationCenter.current()
            center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
            let content = UNMutableNotificationContent()
            content.title = "学习通作业爬取工具"
            content.body = "抓取完成：已处理 \(selectedHomeworkIDs.count) 个作业"
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

    func loadHomeworks() {
        let trimmed = settings.courseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            urlErrorMessage = "请先填写课程 URL，再点击刷新加载作业列表。"
            showURLError = true
            appendLog("请先填写课程 URL", level: "warn")
            return
        }
        // 开始新一轮“加载作业”，复位上轮结束标记与结果计数，
        // 避免刷新时主视图仍停留在「抓取完成」结果卡。
        lastRunFinished = false
        runOkCount = 0
        runFailCount = 0
        runImageFailCount = 0
        isEngineBusy = true
        homeworks.removeAll()
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
        // 新一轮抓取：清零上轮结果计数并复位结束标记
        runOkCount = 0
        runFailCount = 0
        runImageFailCount = 0
        lastRunFinished = false
        fetchStarted = true
        isEngineBusy = true
        isRunning = true
        appendLog("开始抓取 \(selectedHomeworkIDs.count) 个作业…", level: "info")
        engine.send("start", params: ["homework_ids": Array(selectedHomeworkIDs)])
    }

    func stopTask() {
        engine.send("stop")
        appendLog("请求停止…", level: "warn")
    }

    /// 返回作业选择页面（继续抓取）：仅隐藏结果卡，保留已加载的作业与勾选。
    func backToSelection() {
        lastRunFinished = false
    }

    /// 返回主菜单：隐藏结果卡、清空 URL 与作业列表，回到初始空闲状态，便于抓取其他课程。
    func backToMainMenu() {
        lastRunFinished = false
        settings.courseURL = ""
        homeworks.removeAll()
        selectedHomeworkIDs.removeAll()
        runOkCount = 0
        runFailCount = 0
        runImageFailCount = 0
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