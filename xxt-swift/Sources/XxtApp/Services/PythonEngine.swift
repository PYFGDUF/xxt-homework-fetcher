import Foundation
import Combine

/// 管理 Python 引擎子进程（run_bridge.sh -> bridge.py），负责 NDJSON 收发。
/// 通过 `onEvent` 抛回日志/进度/登录提示等事件；命令应答走 `send(_:params:completion:)`。
final class PythonEngine: NSObject {
    /// 事件回调，在主线程调用
    var onEvent: ((EngineEvent) -> Void)?

    /// 进程是否已启动且未退出
    private(set) var isRunning = false

    private let projectDir = "/Users/pengyufeng/Documents/xxt"
    private let bridgeScript = "/Users/pengyufeng/Documents/xxt/run_bridge.sh"
    private let bridgePy = "/Users/pengyufeng/Documents/xxt/bridge.py"

    /// 定位引擎可执行与运行环境。优先 bundle 内自包含引擎（相对路径、数据落到用户应用支持目录）；
    /// 若 bundle 未内置引擎（开发态），回退用本机 anaconda + bridge.py。
    private func resolveLaunch() -> (executableURL: URL, arguments: [String], cwd: URL, browsersDir: String?) {
        if let res = Bundle.main.resourceURL {
            let engine = res.appendingPathComponent("engine_xxt/engine_xxt")
            if FileManager.default.isExecutableFile(atPath: engine.path) {
                let cwd = supportDataDir()
                try? FileManager.default.createDirectory(at: cwd,
                                                         withIntermediateDirectories: true,
                                                         attributes: nil)
                // 登录组件（完整 Chromium）不在内置内；v1.3 起扫码登录与抓取统一走内置无头浏览器，
                // 无需完整 Chromium，浏览器目录仅指向用户可写目录存放无头浏览器与 ffmpeg。
                let browsers = cwd.appendingPathComponent("ms-playwright").path
                ensureBundledBrowsersCopied(bundle: res, target: browsers)
                return (engine, [], cwd, browsers)
            }
        }
        // 回退：开发环境（bundle 未内置引擎时）
        let cwd = URL(fileURLWithPath: projectDir, isDirectory: true)
        let direct = URL(fileURLWithPath: "/Users/pengyufeng/opt/anaconda3/bin/python3")
        if FileManager.default.isExecutableFile(atPath: direct.path),
           FileManager.default.fileExists(atPath: bridgePy) {
            return (direct, [bridgePy], cwd, nil)
        }
        // 兜底：交给 run_bridge.sh 自行发现解释器
        return (URL(fileURLWithPath: "/bin/bash"), [bridgeScript], cwd, nil)
    }

    /// 引擎运行数据目录（settings/state/cookies/progress/logs 等相对文件落在其中），
    /// 可写、独立于 App bundle，分发给其他用户也不会污染应用安装目录。
    private func supportDataDir() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser
        return base.appendingPathComponent("XxtApp", isDirectory: true)
    }

    /// 首次运行：把 App 内置的无头浏览器（chromium_headless_shell / ffmpeg）复制到用户可写目录，
    /// 使默认 headless 抓取离线可用；完整 Chromium（登录组件）不在内置内，由用户按需下载。
    private func ensureBundledBrowsersCopied(bundle: URL, target: String) {
        let srcRoot = bundle.appendingPathComponent("ms-playwright")
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: srcRoot.path) else { return }
        try? FileManager.default.createDirectory(atPath: target,
                                                 withIntermediateDirectories: true,
                                                 attributes: nil)
        for name in names {
            // 跳过完整 Chromium（chromium-<rev>，不含 headless），只复制无头浏览器与 ffmpeg
            if name.hasPrefix("chromium-") && !name.contains("headless") { continue }
            let src = srcRoot.appendingPathComponent(name)
            let dst = target + "/" + name
            var isDir: ObjCBool = false
            guard FileManager.default.fileExists(atPath: src.path, isDirectory: &isDir),
                  isDir.boolValue,
                  !FileManager.default.fileExists(atPath: dst) else { continue }
            try? FileManager.default.copyItem(at: src, to: URL(fileURLWithPath: dst))
        }
    }

    private var process: Process?
    private let inPipe = Pipe()
    private let outPipe = Pipe()
    private let errPipe = Pipe()
    private var stdoutBuf = Data()
    private var nextID = 1
    private let lock = NSLock()
    private var pending = [Int: (EngineReply) -> Void]()

    var onExit: (() -> Void)?

    // MARK: - 生命周期

    func launch() {
        guard !isRunning else { return }
        let resolved = resolveLaunch()
        let p = Process()
        p.executableURL = resolved.executableURL
        p.arguments = resolved.arguments
        p.currentDirectoryURL = resolved.cwd
        if let browsers = resolved.browsersDir {
            var env = ProcessInfo.processInfo.environment
            env["PLAYWRIGHT_BROWSERS_PATH"] = browsers
            p.environment = env
        }
        p.standardInput = inPipe
        p.standardOutput = outPipe
        p.standardError = errPipe
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.isRunning = false
                self?.onExit?()
            }
        }
        do {
            try p.run()
            process = p
            isRunning = true
            readOut()
            readErr()
        } catch {
            isRunning = false
            onEvent?(EngineEvent.rawLog("[error] 无法启动引擎：\(error.localizedDescription)"))
        }
    }

    func terminate() {
        guard let p = process, p.isRunning else { return }
        // 先尝试优雅退出再强杀
        p.interrupt()
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.8) {
            if p.isRunning { p.terminate() }
        }
    }

    // MARK: - 命令发送

    @discardableResult
    func send(_ cmd: String,
              params: [String: Any] = [:],
              completion: ((EngineReply) -> Void)? = nil) -> Int {
        lock.lock()
        let id = nextID
        nextID += 1
        if let completion {
            pending[id] = completion
        }
        lock.unlock()

        var payload: [String: Any] = ["id": id, "cmd": cmd]
        if !params.isEmpty {
            payload["params"] = params
        }
        let data = try? JSONSerialization.data(withJSONObject: payload, options: [])
        if var data {
            data.append(0x0A) // \n
            inPipe.fileHandleForWriting.write(data)
        }
        return id
    }

    /// 退出登录：请求引擎清除本地登录状态文件（state.json 等）并关闭浏览器会话。
    func logout(completion: ((EngineReply) -> Void)? = nil) {
        send("logout", completion: completion)
    }

    /// 取消登录：请求引擎终止当前登录流程并取消相关抓取任务。
    func loginCancel() {
        send("login_cancel")
    }

    /// 查询当前是否已保存登录态（state.json 可读且非空）。
    func loginStatus(completion: @escaping (Bool) -> Void) {
        send("login_status") { reply in
            let loggedIn = (reply.result?["logged_in"] as? NSNumber)?.boolValue ?? false
            completion(reply.ok && loggedIn)
        }
    }

    /// 独立发起扫码登录（设置中「登录学习通」）。
    func startLogin() {
        send("login")
    }

    // MARK: - 读取输出

    private func readOut() {
        outPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard data.count > 0, let self else { return }
            self.stdoutBuf.append(data)
            while let newline = self.stdoutBuf.firstIndex(of: 0x0A) {
                let lineData = self.stdoutBuf.subdata(in: 0..<newline)
                self.stdoutBuf.removeSubrange(0...(newline))
                self.handleLine(lineData)
            }
        }
    }

    private func readErr() {
        errPipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard data.count > 0, let self else { return }
            let text = String(data: data, encoding: .utf8) ?? ""
            // 逐行处理，避免一次 read 里混入多行
            let lines = text.split(separator: "\n", omittingEmptySubsequences: false)
            var parsed = [(level: String, message: String)]()
            for ln in lines {
                if let p = Self.parseLevelLine(String(ln)) {
                    parsed.append(p)
                }
            }
            guard !parsed.isEmpty else { return }
            DispatchQueue.main.async {
                for item in parsed {
                    self.onEvent?(EngineEvent(kind: .log,
                                              value: EngineEventValue(message: item.message, level: item.level)))
                }
            }
        }
    }

    /// 解析可能是 `时间戳 [LEVEL] 消息` 格式的 stderr 行，返回真实级别与去掉时间戳/级别前缀后的消息。
    /// 这样即便有进程把 LOGGER 的格式化日志写到 stderr，也能按真实级别展示，而非一律标 [error]。
    static func parseLevelLine(_ raw: String) -> (level: String, message: String)? {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let pattern = #"\[(DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL)\]"#
        guard let range = trimmed.range(of: pattern, options: [.regularExpression, .caseInsensitive]) else {
            return ("error", trimmed)
        }
        let token = String(trimmed[range]).uppercased()
        let level: String
        if token == "[DEBUG]" {
            level = "debug"
        } else if token == "[INFO]" {
            level = "info"
        } else if token == "[WARN]" || token == "[WARNING]" {
            level = "warn"
        } else {
            level = "error"
        }
        var message = trimmed
        message.removeSubrange(range)
        message = message.trimmingCharacters(in: .whitespaces)
        // 去掉 LOGGER 前缀可能残留的时间戳，如 "2026-08-20 00:51:16"
        message = message.replacingOccurrences(of: #"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?\s*"#,
                                               with: "",
                                               options: .regularExpression)
        message = message.trimmingCharacters(in: .whitespaces)
        return (level, message.isEmpty ? trimmed : message)
    }

    private func handleLine(_ lineData: Data) {
        guard let obj = try? JSONSerialization.jsonObject(with: lineData, options: []) as? [String: Any] else {
            return
        }
        if obj["kind"] is String {
            let event = decodedEvent(obj)
            // readabilityHandler 运行在后台队列，切到主线程再交给 AppState，
            // 避免后台修改 homeworks/logs 与主线程 SwiftUI 渲染竞争导致崩溃。
            DispatchQueue.main.async { [weak self] in
                self?.onEvent?(event)
            }
        } else if obj["id"] is Int {
            dispatchReply(obj)
        }
    }

    private func decodedEvent(_ obj: [String: Any]) -> EngineEvent {
        if let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
           let event = try? JSONDecoder().decode(EngineEvent.self, from: data) {
            return event
        }
        return EngineEvent.rawLog("[warn] 无法解析事件")
    }

    private func dispatchReply(_ obj: [String: Any]) {
        let id = (obj["id"] as? Int) ?? -1
        let ok = (obj["ok"] as? Bool) ?? false
        let result = obj["result"] as? [String: Any]
        let error = obj["error"] as? String
        let reply = EngineReply(id: id, ok: ok, result: result, error: error)

        var completion: ((EngineReply) -> Void)?
        lock.lock()
        completion = pending.removeValue(forKey: id)
        lock.unlock()

        if let completion {
            DispatchQueue.main.async { completion(reply) }
        }
    }
}

extension EngineEvent {
    /// 构造一条普通日志事件（供本地错误提示复用）
    static func rawLog(_ message: String) -> EngineEvent {
        return EngineEvent(kind: .log,
                           value: EngineEventValue(message: message, level: "error"))
    }
}