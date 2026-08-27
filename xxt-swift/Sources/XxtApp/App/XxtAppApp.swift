import SwiftUI

/// 学习通作业抓取工具 —— 原生 macOS 重写
/// SwiftUI 界面（含 Liquid Glass / 材质背景）+ 复用现有 Python/Playwright 引擎（JSON 子进程通信）
@main
struct XxtApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @State private var appState = AppState()

    var body: some Scene {
        WindowGroup(id: "main") {
            ContentView()
                .environment(appState)
                .frame(minWidth: 900, minHeight: 620)
        }
        .windowStyle(.automatic)
        .windowToolbarStyle(.unifiedCompact)
        .defaultSize(width: 1040, height: 720)
        // 系统统一的“设置”偏好窗口（Cmd+, 自动生效）
        Settings {
            SettingsView()
                .environment(appState)
        }
        .commands {
            CommandGroup(replacing: .newItem) { }
            // 系统“设置”菜单项汉化（Cmd+, 自动生效）
            CommandGroup(replacing: .appSettings) {
                SettingsLink {
                    Text("设置…")
                }
                .keyboardShortcut(",", modifiers: [.command])
            }
            // 常用操作放进独立的“操作”菜单，遵循 macOS 菜单惯例（正文工具类动作不放应用菜单）
            CommandMenu("操作") {
                Button("前往输出目录") {
                    appState.openLastOutput()
                }
                .keyboardShortcut("o", modifiers: [.command])
                Button("清空日志") {
                    appState.clearLogs()
                }
                .keyboardShortcut("k", modifiers: [.command])
                Divider()
                Button {
                    appState.stopAction()
                } label: {
                    Text(appState.stopArmed ? "确认停止" : "停止任务")
                }
                .keyboardShortcut(".", modifiers: [.command])
                .disabled(!appState.isRunning)
            }
            // 原位替换系统“帮助”菜单内容，去掉默认的搜索/占位项
            // （否则会显示“未找到 XxtApp 的帮助”占位），替换为打开帮助文档。
            CommandGroup(replacing: .help) {
                Button("打开帮助文档") {
                    appState.openHelpDocument()
                }
                .keyboardShortcut("?", modifiers: [.command])
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 单实例控制：若已存在同一 bundle id 的实例，则激活它并退出本进程，
        // 使“再次打开/双击”直接跳转到先前已经打开的程序。
        enforceSingleInstance()
    }

    private func enforceSingleInstance() {
        let myID = Bundle.main.bundleIdentifier ?? "com.local.xxt.app"
        let myPID = ProcessInfo.processInfo.processIdentifier
        let others = NSWorkspace.shared.runningApplications.filter { app in
            guard app.bundleIdentifier == myID,
                  app.processIdentifier != myPID,
                  app.isTerminated == false else { return false }
            return true
        }
        guard let existing = others.first else { return }
        DispatchQueue.main.async {
            existing.activate(options: [.activateAllWindows])
            self.activateMainWindow()
            NSApplication.shared.terminate(nil)
        }
    }

    /// 双击应用再次打开时：已有实例直接跳到前台（返回 false 阻止系统再开新窗）。
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        NSApp.activate(ignoringOtherApps: true)
        activateMainWindow()
        return false
    }

    /// 若应用被注册用来打开文件，二次打开时跳到已有窗口。
    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        NSApp.activate(ignoringOtherApps: true)
        activateMainWindow()
    }

    private func activateMainWindow() {
        if let w = NSApp.windows.first(where: { $0.isVisible }) {
            w.makeKeyAndOrderFront(nil)
        }
    }
}