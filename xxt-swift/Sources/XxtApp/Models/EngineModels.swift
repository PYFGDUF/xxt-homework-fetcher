import Foundation

/// 与 Python 端 settings.json / 引擎交互的配置模型
struct EngineSettings: Codable, Equatable {
    var courseURL: String = ""
    var outputDir: String = ""
    var autoExportPDF: Bool = false
    var forceRegrab: Bool = false
    var openDirOnComplete: Bool = true
    var showSourceURL: Bool = true
    var appearance: String = "system"
    /// 实验室：多线程并发抓取（默认关闭；开启后并发线程数 2..4）
    var concurrencyEnabled: Bool = false
    var concurrencyWorkers: Int = 2

    enum CodingKeys: String, CodingKey {
        case courseURL = "course_url"
        case outputDir = "output_dir"
        case autoExportPDF = "auto_export_pdf"
        case forceRegrab = "force_regrab"
        case openDirOnComplete = "open_dir_on_complete"
        case showSourceURL = "show_source_url"
        case appearance
        case concurrencyEnabled = "concurrency_enabled"
        case concurrencyWorkers = "concurrency_workers"
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
        case log, progress, loginPrompt, loginQr, loginSuccess, homeworkList, homeworkPage, done, error, status, imageFail, courseList
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
    var courses: [CourseItem]?
    var requestLogin: Bool?
    var success: Bool?
    var outputDir: String?
    var url: String?
    var status: String?
    var progress: Double?      // 单个作业内部进度 0~1（status 事件附带）
    var overall: Double?       // 总进度 0~1（由单作业进度实时映射，供总进度条联动）
    var installed: Bool?
    var imageB64: String?
    var failed: Int?

    enum CodingKeys: String, CodingKey {
        case message, level, current, total, title, items, courses, success
        case requestLogin = "request_login"
        case outputDir = "output_dir"
        case url, status, installed, failed, overall
        case imageB64 = "image_b64"
        case progress
    }
}

/// 课程条目（个人空间课程列表，来自 courseList 事件）
struct CourseItem: Decodable, Identifiable, Hashable {
    let url: String
    var title: String
    var teacher: String
    var cover: String   // 真实课程封面缩略图 URL
    var ended: Bool     // 是否为「课程已结束」的结束课程
    let courseID: String
    let clazzID: String
    let cpi: String

    var id: String { url }

    enum CodingKeys: String, CodingKey {
        case url, title, teacher, cover
        case ended
        case courseID = "courseid"
        case clazzID = "clazzid"
        case cpi
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        url = (try? c.decode(String.self, forKey: .url)) ?? ""
        title = (try? c.decode(String.self, forKey: .title)) ?? ""
        teacher = (try? c.decode(String.self, forKey: .teacher)) ?? ""
        cover = (try? c.decode(String.self, forKey: .cover)) ?? ""
        ended = (try? c.decode(Bool.self, forKey: .ended)) ?? false
        courseID = (try? c.decode(String.self, forKey: .courseID)) ?? ""
        clazzID = (try? c.decode(String.self, forKey: .clazzID)) ?? ""
        cpi = (try? c.decode(String.self, forKey: .cpi)) ?? ""
    }
}

/// 作业条目
struct HomeworkItem: Decodable, Identifiable, Hashable {
    let id: String
    var title: String
    var status: String
    var progress: Double       // 单个作业内部进度 0~1（引擎 status 事件上报）
    var url: String?
    var listURL: String?

    enum CodingKeys: String, CodingKey {
        case id, title, status, url, progress
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
        progress = (try? c.decode(Double.self, forKey: .progress)) ?? 0
        url = try? c.decode(String.self, forKey: .url)
        listURL = try? c.decode(String.self, forKey: .listURL)
    }

    /// 作业内进度百分比（0...100，进度钳制在 0~1）
    var progressPercent: Int {
        Int((min(max(progress, 0), 1) * 100).rounded())
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