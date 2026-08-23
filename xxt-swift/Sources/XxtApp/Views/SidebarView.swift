import SwiftUI

struct SidebarView: View {
    @Environment(AppState.self) private var app
    @State private var searchText = ""

    private var filteredHomeworks: [HomeworkItem] {
        guard !searchText.isEmpty else { return app.homeworks }
        return app.homeworks.filter {
            $0.title.localizedCaseInsensitiveContains(searchText.trimmingCharacters(in: .whitespaces))
        }
    }

    /// 当前列表是否已全部选中（用于禁用“全选”按钮）
    private var isAllSelected: Bool {
        !filteredHomeworks.isEmpty && filteredHomeworks.allSatisfy {
            app.selectedHomeworkIDs.contains($0.id)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            List {
                if app.homeworks.isEmpty && !app.isEngineBusy {
                    ContentUnavailableView(
                        "暂无作业",
                        systemImage: "square.stack.3d.up",
                        description: Text("在底部输入课程 URL 后点击“加载作业”")
                    )
                } else if filteredHomeworks.isEmpty {
                    ContentUnavailableView.search(text: searchText)
                } else {
                    ForEach(filteredHomeworks) { hw in
                        HomeworkRow(item: hw)
                    }
                }
            }
            .listStyle(.sidebar)
            .searchable(text: $searchText, placement: .sidebar, prompt: "搜索作业")

            // 底部“创作条”：去掉手绘硬分隔线，改用原生材质条，与 macOS 底部输入区一致
            HStack(spacing: 6) {
                Image(systemName: "link")
                    .foregroundStyle(.secondary)
                    .help("课程链接")
                TextField("课程 URL", text: Bindable(app).settings.courseURL, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...3)
                    .font(.caption)
                    .submitLabel(.go)
                    .onSubmit {
                        if !app.isEngineBusy {
                            app.loadHomeworks()
                        }
                    }
                Button {
                    app.loadHomeworks()
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(app.isEngineBusy)
                .help("加载作业列表")
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(.bar)
        }
        .navigationSplitViewColumnWidth(min: 240, ideal: 300, max: 420)
        .safeAreaInset(edge: .bottom) {
            if !app.homeworks.isEmpty {
                HStack(spacing: 10) {
                    Text("\(filteredHomeworks.count) 个作业")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.disabled)
                    Spacer()
                    Button {
                        app.selectedHomeworkIDs.formUnion(filteredHomeworks.map(\.id))
                    } label: {
                        Label("全选", systemImage: "checkmark.circle")
                    }
                    .help("选中当前列表的全部作业")
                    .disabled(isAllSelected)
                    Button {
                        app.selectedHomeworkIDs.removeAll()
                    } label: {
                        Label("清空", systemImage: "clear")
                    }
                    .help("清空当前已选中的作业")
                    .disabled(app.selectedHomeworkIDs.isEmpty)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
            }
        }
    }
}

private struct HomeworkRow: View {
    @Environment(AppState.self) private var app
    let item: HomeworkItem

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            Toggle("", isOn: isSelectedBinding)
                .toggleStyle(.checkbox)
                .labelsHidden()
                .accessibilityLabel(item.title)
            Text(item.title)
                .font(.body)
                .lineLimit(2)
            Spacer(minLength: 4)
            statusBadge
        }
        .padding(.vertical, 1)
    }

    @ViewBuilder
    private var statusBadge: some View {
        if !item.status.isEmpty {
            Image(systemName: statusIcon)
                .foregroundStyle(statusColor)
                .font(.footnote)
                .symbolEffect(.bounce, options: .nonRepeating, value: item.status)
                .accessibilityLabel(item.status)
                .help(item.status)
        }
    }

    private var statusIcon: String {
        switch item.status {
        case "completed": return "checkmark.circle.fill"
        case "failed": return "xmark.circle.fill"
        default: return "hourglass.circle"
        }
    }

    private var statusColor: Color {
        switch item.status {
        case "completed": return .green
        case "failed": return .red
        default: return .secondary
        }
    }

    private var isSelectedBinding: Binding<Bool> {
        Binding(
            get: { app.selectedHomeworkIDs.contains(item.id) },
            set: { isOn in
                if isOn {
                    app.selectedHomeworkIDs.insert(item.id)
                } else {
                    app.selectedHomeworkIDs.remove(item.id)
                }
            }
        )
    }
}