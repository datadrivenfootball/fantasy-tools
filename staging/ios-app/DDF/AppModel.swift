import SwiftUI
import WebKit

/// Owns the page's web view and answers its one request: "connect ESPN".
///
/// The page calls `window.webkit.messageHandlers.ddfEspn.postMessage({want: "session"})` and awaits the
/// answer. If ESPN is already signed in inside the app, the answer is immediate. Otherwise the app shows
/// ESPN's own sign-in page in a sheet, waits for ESPN to set its session cookies, and then answers.
/// The page sends the session to DDF's server, which checks it with ESPN and stores it sealed.
@MainActor
final class AppModel: NSObject, ObservableObject {
    @Published var showingEspnSignIn = false
    @Published var pageFailed: String?

    let dataStore = WKWebsiteDataStore.default()
    private(set) lazy var pageView: WKWebView = makePageView()
    private var waiting: CheckedContinuation<EspnSession?, Never>?

    private func makePageView() -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = dataStore
        config.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "ddfEspn")
        #if DEBUG
        if Config.harnessSignedIn {
            config.userContentController.addUserScript(WKUserScript(source: "try{localStorage.h_in='1'}catch(e){}", injectionTime: .atDocumentStart, forMainFrameOnly: true))
        }
        #endif
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = self
        view.uiDelegate = self
        view.allowsBackForwardNavigationGestures = true
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.969, green: 0.973, blue: 0.961, alpha: 1)   // --canvas, so there is no white flash
        return view
    }

    func start() async {
        #if DEBUG
        if Config.plantTestSession { await EspnSession.plantTestSession(in: dataStore.httpCookieStore) }
        #endif
        loadPage()
    }

    func loadPage(fragment: String? = nil) {
        pageFailed = nil
        var url = Config.page
        if let fragment, var parts = URLComponents(url: url, resolvingAgainstBaseURL: false) {
            parts.fragment = fragment
            url = parts.url ?? url
        }
        pageView.load(URLRequest(url: url))
    }

    /// The DDF sign-in email links back to the app as ddf://signin#…; hand that fragment to the page.
    func open(_ url: URL) {
        guard url.scheme == "ddf", url.host == "signin" else { return }
        loadPage(fragment: url.fragment)
    }

    // MARK: ESPN sign-in sheet

    private func espnSession() async -> EspnSession? {
        if let session = await EspnSession.current(in: dataStore.httpCookieStore) { return session }
        guard waiting == nil else { return nil }
        showingEspnSignIn = true
        return await withCheckedContinuation { waiting = $0 }
    }

    /// Called by the sheet when ESPN's session appears, or with nil when the user closes it.
    func finishEspnSignIn(_ session: EspnSession?) {
        showingEspnSignIn = false
        waiting?.resume(returning: session)
        waiting = nil
    }
}

extension AppModel: WKScriptMessageHandlerWithReply {
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) async -> (Any?, String?) {
        // Only DDF's own page, in the main frame, may ask.
        let origin = message.frameInfo.securityOrigin
        let asked = origin.port == 0 ? "\(origin.protocol)://\(origin.host)" : "\(origin.protocol)://\(origin.host):\(origin.port)"
        guard message.frameInfo.isMainFrame, asked == Config.pageOrigin else { return (nil, "not allowed") }
        let want = (message.body as? [String: Any])?["want"] as? String
        switch want {
        case "session":
            guard let session = await espnSession() else { return (["cancelled": true], nil) }
            return (["espn_s2": session.espnS2, "swid": session.swid], nil)
        case "forget":
            await EspnSession.forget(in: dataStore.httpCookieStore)
            return (["ok": true], nil)
        default:
            return (nil, "unknown request")
        }
    }
}

extension AppModel: WKNavigationDelegate, WKUIDelegate {
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
        guard let url = action.request.url, action.targetFrame?.isMainFrame ?? true else { return .allow }
        // Links that leave DDF open in Safari; redirects (sign-in round trips) stay in the app.
        if action.navigationType == .linkActivated, Config.origin(of: url) != Config.pageOrigin, ["http", "https"].contains(url.scheme ?? "") {
            await UIApplication.shared.open(url)
            return .cancel
        }
        return .allow
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { UIApplication.shared.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code == NSURLErrorCancelled { return }
        pageFailed = "DDF couldn't load. Check your connection."
    }

    // The page uses confirm() before removing things.
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo) async -> Bool {
        await withCheckedContinuation { done in
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in done.resume(returning: false) })
            alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in done.resume(returning: true) })
            guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first,
                  var top = scene.keyWindow?.rootViewController else { return done.resume(returning: false) }
            while let next = top.presentedViewController { top = next }
            top.present(alert, animated: true)
        }
    }
}
