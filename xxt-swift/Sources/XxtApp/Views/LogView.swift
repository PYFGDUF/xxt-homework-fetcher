import SwiftUI

struct LogView: View {
    @Environment(AppState.self) private var app
    @State private var atBottom = true

    var body: some View {
        if app.logs.isEmpty {
            ContentUnavailableView(
                "暂无日志",
                systemImage: "text.alignleft",
                description: Text("加载或抓取作业时，运行日志会显示在这里")
            )
        } else {
            scrollable
        }
    }

    private var scrollable: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    ForEach(app.logs) { line in
                        logLine(line)
                            .id(line.id)
                    }
                }
                .padding(12)
            }
            .modifier(SoftEdgeTopModifier())
            .scrollContentBackground(.hidden)
            .safeAreaInset(edge: .bottom) {
                if !atBottom {
                    Button {
                        if let last = app.logs.last {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    } label: {
                        Label("跳到底部", systemImage: "arrow.down")
                    }
                    .font(.caption)
                    .buttonStyle(.borderedProminent)
                    .padding(.bottom, 6)
                }
            }
            .onAppear {
                // 面板/页面出现时定位到最新日志，避免打开「运行详情」后停留在顶部
                if app.logAutoScroll, let last = app.logs.last {
                    proxy.scrollTo(last.id, anchor: .bottom)
                    atBottom = true
                }
            }
            .onChange(of: app.logs.count) {
                if app.logAutoScroll, let last = app.logs.last {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private func logLine(_ line: LogLine) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Text(line.time)
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.tertiary)
            Text(line.message)
                .font(.body.monospaced())
                .foregroundStyle(levelColor(line.level))
                .textSelection(.enabled)
        }
    }

    private func levelColor(_ level: String) -> Color {
        switch level {
        case "error": return .red
        case "warn": return .orange
        case "success": return .green
        case "progress": return .blue
        default: return .primary
        }
    }
}

/// 顶部柔和毛边效果：仅在 macOS 26+（Liquid Glass 平台）启用，旧系统自动回退，保证最低部署版本不变。
private struct SoftEdgeTopModifier: ViewModifier {
    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(macOS 26.0, *) {
            content.scrollEdgeEffectStyle(.soft, for: .top)
        } else {
            content
        }
    }
}