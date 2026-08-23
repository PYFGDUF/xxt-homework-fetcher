import Foundation

/// 与 Python 端 settings.json / 引擎交互的配置模型
struct EngineSettings: Codable, Equatable {
    var courseURL: String = ""
    var outputDir: String = ""
    var autoExportPDF: Bool = false
    var forceRegrab: Bool = false
    var openDirOnComplete: Bool = true
    var appearance: String = "system"

    enum CodingKeys: String, CodingKey {
        case courseURL = "course_url"
        case outputDir = "output_dir"
        case autoExportPDF = "auto_export_pdf"
        case forceRegrab = "force_regrab"
        case openDirOnComplete = "open_dir_on_complete"
        case appearance
    }
}

/// 引擎子进程对一条命令的应答：{"id":…, "ok":…, "result"/"error":…}
struct EngineReply {
    let id: Int
    let ok: Bool
    let result: [String: Any]?
    let error: String?
}

/// Python 引擎发回的事件
struct EngineEvent: Decodable {
    enum Kind: String, Decodable {
        case log, progress, loginPrompt, loginQr, loginSuccess, homeworkList, homeworkPage, done, error, status, imageFail
    }
    let kind: Kind
    let value: EngineEventValue

    init(kind: Kind, value: EngineEventValue) {
        self.kind = kind
        self.value = value
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = try c.decode(Kind.self, forKey: .kind)
        value = try c.decode(EngineEventValue.self, forKey: .value)
    }

    private enum CodingKeys: String, CodingKey { case kind, value }
}

/// 事件负载（宽松字段，按 kind 读取）
struct EngineEventValue: Decodable {
    var message: String?
    var level: String?
    var current: Int?
    var total: Int?
    var title: String?
    var items: [HomeworkItem]?
    var requestLogin: Bool?
    var success: Bool?
    var outputDir: String?
    var url: String?
    var status: String?
    var installed: Bool?
    var imageB64: String?
    var failed: Int?

    enum CodingKeys: String, CodingKey {
        case message, level, current, total, title, items, success
        case requestLogin = "request_login"
        case outputDir = "output_dir"
        case url, status, installed, failed
        case imageB64 = "image_b64"
    }
}

/// 作业条目
struct HomeworkItem: Decodable, Identifiable, Hashable {
    let id: String
    var title: String
    var status: String
    var url: String?
    var listURL: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, url
        case listURL = "list_url"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let i = try? c.decode(Int.self, forKey: .id) {
            id = String(i)
        } else if let s = try? c.decode(String.self, forKey: .id), !s.isEmpty {
            id = s
        } else {
            // Python 端无 id 时退化为用 URL 生成
            let u = (try? c.decode(String.self, forKey: .url)) ?? ""
            id = u.isEmpty ? UUID().uuidString : u
        }
        title = (try? c.decode(String.self, forKey: .title)) ?? ""
        status = (try? c.decode(String.self, forKey: .status)) ?? ""
        url = try? c.decode(String.self, forKey: .url)
        listURL = try? c.decode(String.self, forKey: .listURL)
    }
}

/// 待修复作业
struct RepairItem: Decodable, Identifiable, Hashable {
    let path: String
    var title: String
    var url: String

    var id: String { path }
}

/// progress.json 历史记录
struct ProgressItem: Decodable, Identifiable, Hashable {
    var title: String
    var status: String
    var url: String
    var lastRun: String?
    var outputDir: String?
    var wordFile: String?

    var id: String { url }

    enum CodingKeys: String, CodingKey {
        case title, status, url
        case lastRun = "last_run"
        case outputDir = "output_dir"
        case wordFile = "word_file"
    }
}

/// 日志行
struct LogLine: Identifiable, Equatable {
    let id: Int
    let time: String
    let level: String
    let message: String
}