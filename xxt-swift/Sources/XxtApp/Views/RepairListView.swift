import SwiftUI

struct RepairListView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        Group {
            if app.repairItems.isEmpty {
                ContentUnavailableView(
                    "没有待修复的作业",
                    systemImage: "checkmark.seal",
                    description: Text("点击工具栏“扫描”检测答案缺失的作业")
                )
            } else {
                List(selection: Bindable(app).repairSelection) {
                    ForEach(app.repairItems) { item in
                        RepairRow(item: item)
                            .tag(item.path)
                    }
                }
                .listStyle(.inset)
            }
        }
    }
}

private struct RepairRow: View {
    let item: RepairItem

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.body)
                Text(URL(string: item.url)?.host ?? item.url)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(item.path)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
    }
}

struct HistoryView: View {
    @Environment(AppState.self) private var app
    @State private var showClearConfirm = false

    var body: some View {
        Group {
            if app.progressItems.isEmpty {
                ContentUnavailableView(
                    "暂无记录",
                    systemImage: "clock",
                    description: Text("完成一次抓取后，这里会显示历史作业")
                )
            } else {
                List {
                    ForEach(app.progressItems) { item in
                        HStack {
                            Image(systemName: item.status == "completed" ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundStyle(item.status == "completed" ? .green : .red)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(item.title)
                                if let word = item.wordFile {
                                    Text(word)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                            if let word = item.wordFile, item.status == "completed" {
                                Button("打开") {
                                    NSWorkspace.shared.open(URL(fileURLWithPath: Self.resolve(word)))
                                }
                                .buttonStyle(.borderless)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                    // 最后一个历史项下方：圆形叉号按钮，用于删除全部历史记录
                    HStack {
                        Spacer()
                        Button {
                            showClearConfirm = true
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundStyle(.secondary)
                                .frame(width: 30, height: 30)
                                .background(Circle().fill(.quaternary))
                        }
                        .buttonStyle(.plain)
                        .help("清空历史记录")
                        Spacer()
                    }
                    .padding(.vertical, 8)
                    .listRowSeparator(.hidden)
                }
                .listStyle(.inset)
            }
        }
        .confirmationDialog("删除全部历史记录？", isPresented: $showClearConfirm) {
            Button("删除全部", role: .destructive) {
                app.clearHistory()
            }
            Button("取消", role: .cancel) {}
        }
    }

    static func resolve(_ path: String) -> String {
        path.hasPrefix("/") ? path : "\(AppState.defaultProjectDir)/\(path)"
    }
}