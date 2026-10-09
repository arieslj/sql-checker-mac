import Cocoa
import WebKit

let startupBegan = ProcessInfo.processInfo.systemUptime
var startupMetrics: [String: Double] = [:]
func recordStartup(_ phase: String) {
#if STARTUP_PROFILE
    startupMetrics[phase] = ProcessInfo.processInfo.systemUptime - startupBegan
    if let data = try? JSONSerialization.data(withJSONObject: startupMetrics, options: [.prettyPrinted, .sortedKeys]) {
        let name = "sqlchecker-" + (Bundle.main.bundleIdentifier ?? "test") + "-startup.json"
        try? data.write(to: URL(fileURLWithPath: "/private/tmp/").appendingPathComponent(name), options: .atomic)
    }
#endif
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var backend: Process?
    var expectedURL: URL?
    var launching = true
    var engineReady = false
    var backendFailed = false
    var readiness = Data()
    var outputPipe: Pipe?
    var pending: [[String: String]] = []
    var uiRoot: URL!
    lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 60
        config.connectionProxyDictionary = [:]
        return URLSession(configuration: config)
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        let mainMenu = NSMenu()
        let appMenuItem = NSMenuItem()
        mainMenu.addItem(appMenuItem)
        let appMenu = NSMenu()
        appMenu.addItem(NSMenuItem(title: "退出 SQL 检查器", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        appMenuItem.submenu = appMenu
        let editItem = NSMenuItem()
        mainMenu.addItem(editItem)
        let editMenu = NSMenu(title: "编辑")
        for (title, action, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            editMenu.addItem(NSMenuItem(title: title, action: Selector(action), keyEquivalent: key))
        }
        editItem.submenu = editMenu
        NSApp.mainMenu = mainMenu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1120, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "SQL 检查器 · 本地运行"
        window.minSize = NSSize(width: 680, height: 520)
        window.center()
        window.delegate = self
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.userContentController.add(self, name: "sqlChecker")
        configuration.userContentController.addUserScript(WKUserScript(source: "window.SQL_CHECKER_DESKTOP=true; window.SQL_CHECKER_ENGINE_READY=false;", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        web = WKWebView(frame: window.contentView!.bounds, configuration: configuration)
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        window.contentView!.addSubview(web)
        window.makeKeyAndOrderFront(nil)
        recordStartup("window_shown")
        NSApp.activate(ignoringOtherApps: true)
        let resource = Bundle.main.resourceURL!
        uiRoot = resource.appendingPathComponent("ui", isDirectory: true)
        web.loadFileURL(uiRoot.appendingPathComponent("index.html"), allowingReadAccessTo: uiRoot)
        let process = Process()
        process.executableURL = resource.appendingPathComponent("backend/SQLCheckerBackend/SQLCheckerBackend")
        process.currentDirectoryURL = resource
        let pipe = Pipe()
        outputPipe = pipe
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, !self.backendFailed else { return }
                self.fail("检查引擎已停止，可复制 SQL 后重新打开应用。")
            }
        }
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if data.isEmpty { handle.readabilityHandler = nil; return }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.readiness.append(data)
                while let newline = self.readiness.firstIndex(of: 10) {
                    let line = String(data: self.readiness[..<newline], encoding: .utf8) ?? ""
                    self.readiness.removeSubrange(...newline)
                    self.receiveBackendLine(line)
                }
            }
        }
        backend = process
        do { try process.run() } catch { fail("无法启动应用内置引擎：\(error.localizedDescription)") }
        DispatchQueue.main.asyncAfter(deadline: .now() + 45) { [weak self] in
            if self?.launching == true { self?.fail("检查引擎启动超时，可复制 SQL 后重新打开应用。") }
        }
    }

    func receiveBackendLine(_ line: String) {
        if line == "ENGINE_READY" {
            engineReady = true
            recordStartup("engine_ready")
            web.evaluateJavaScript("window.sqlCheckerEngineReady?.()", completionHandler: nil)
        } else if line == "ENGINE_FAILED" {
            fail("检查引擎初始化失败，可复制 SQL 后重新打开应用。")
        } else if let url = URL(string: line), url.scheme == "http", url.host == "127.0.0.1", url.port != nil {
            expectedURL = url
            launching = false
            recordStartup("backend_ready")
            let waiting = pending
            pending.removeAll()
            for message in waiting { send(message) }
        }
    }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.frameInfo.securityOrigin.protocol == "file",
              let body = message.body as? [String: String], let id = body["id"], id.count <= 30,
              let action = body["action"], ["check", "format"].contains(action), let sql = body["sql"] else { return }
        if sql.count > 50000 { reply(id, payload: ["error": "SQL 超过 50,000 字符，请拆分检查"], status: 400); return }
        if backendFailed { reply(id, payload: ["error": "检查引擎已停止，请重新打开应用"], status: 503); return }
        if expectedURL == nil {
            if pending.count >= 8 { reply(id, payload: ["error": "引擎正在启动，请稍后重试"], status: 429) }
            else { pending.append(body) }
        } else { send(body) }
    }

    func send(_ body: [String: String]) {
        guard let base = expectedURL, let id = body["id"], let action = body["action"], let sql = body["sql"] else { return }
        var request = URLRequest(url: base.appendingPathComponent("api/" + action))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["sql": sql])
        session.dataTask(with: request) { [weak self] data, response, error in
            let status = (response as? HTTPURLResponse)?.statusCode ?? 503
            let payload = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } ?? ["error": "本地检查未完成，请重试"]
            DispatchQueue.main.async {
                recordStartup("first_reply")
                self?.reply(id, payload: payload, status: status)
            }
        }.resume()
    }

    func reply(_ id: String, payload: Any, status: Int) {
        guard let data = try? JSONSerialization.data(withJSONObject: [id, payload, status], options: [.fragmentsAllowed]),
              let json = String(data: data, encoding: .utf8) else { return }
        let safe = json.replacingOccurrences(of: "\u{2028}", with: "\\u2028").replacingOccurrences(of: "\u{2029}", with: "\\u2029")
        web.evaluateJavaScript("window.sqlCheckerReply?.apply(null, \(safe))", completionHandler: nil)
    }

    func fail(_ message: String) {
        launching = false
        backendFailed = true
        let waiting = pending
        pending.removeAll()
        for body in waiting { if let id = body["id"] { reply(id, payload: ["error": message], status: 503) } }
        web.evaluateJavaScript("window.sqlCheckerEngineFailed?.()", completionHandler: nil)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        recordStartup("ui_ready")
        if engineReady { web.evaluateJavaScript("window.sqlCheckerEngineReady?.()", completionHandler: nil) }
        if backendFailed { web.evaluateJavaScript("window.sqlCheckerEngineFailed?.()", completionHandler: nil) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        let root = uiRoot?.standardizedFileURL.path ?? ""
        if url.isFileURL && url.standardizedFileURL.path.hasPrefix(root + "/") { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        backendFailed = true
        launching = false
        outputPipe?.fileHandleForReading.readabilityHandler = nil
        web.configuration.userContentController.removeScriptMessageHandler(forName: "sqlChecker")
        session.invalidateAndCancel()
        if backend?.isRunning == true { backend?.terminate() }
    }
}
let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.setActivationPolicy(.regular)
application.run()
