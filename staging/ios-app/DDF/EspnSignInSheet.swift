import SwiftUI
import WebKit

/// ESPN's own sign-in page, shown inside the app. The user types their ESPN details into ESPN's page;
/// the app watches only the cookie store, and closes the sheet as soon as ESPN has signed them in.
struct EspnSignInSheet: View {
    @ObservedObject var model: AppModel
    @StateObject private var watcher = EspnSignInWatcher()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                HStack(spacing: 6) {
                    Image(systemName: "lock.fill").font(.caption2)
                    Text(watcher.host).font(.footnote.monospaced())
                    Spacer()
                    Text("DDF never sees your password").font(.caption).foregroundStyle(.secondary)
                }
                .padding(.horizontal, 16).padding(.vertical, 8)
                .background(Color(red: 0.91, green: 0.96, blue: 0.93))
                .foregroundStyle(Color(red: 0.09, green: 0.42, blue: 0.30))
                EspnWebView(model: model, watcher: watcher)
            }
            .navigationTitle("Sign in at ESPN")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { model.finishEspnSignIn(nil) } }
                #if DEBUG
                if Config.testSignInButton {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Test sign-in") { Task { await EspnSession.plantTestSession(in: model.dataStore.httpCookieStore); await watcher.check() } }
                    }
                }
                #endif
            }
        }
        .interactiveDismissDisabled()
        .onAppear { watcher.start(model: model) }
        .onDisappear { watcher.stop() }
    }
}

/// Watches the shared cookie store and reports the moment ESPN's session appears. The store's change
/// notice is the fast path; a once-a-second check backs it up, because the notice is not always delivered.
@MainActor
final class EspnSignInWatcher: NSObject, ObservableObject, WKHTTPCookieStoreObserver {
    @Published var host = "www.espn.com"
    private weak var model: AppModel?
    private var poll: Task<Void, Never>?

    func start(model: AppModel) {
        self.model = model
        model.dataStore.httpCookieStore.add(self)
        poll = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                await self?.check()
            }
        }
    }

    func stop() {
        poll?.cancel()
        model?.dataStore.httpCookieStore.remove(self)
    }

    func check() async {
        guard let model, model.showingEspnSignIn, let session = await EspnSession.current(in: model.dataStore.httpCookieStore) else { return }
        model.finishEspnSignIn(session)
    }

    nonisolated func cookiesDidChange(in cookieStore: WKHTTPCookieStore) {
        Task { @MainActor in await check() }
    }
}

struct EspnWebView: UIViewRepresentable {
    let model: AppModel
    let watcher: EspnSignInWatcher

    func makeCoordinator() -> Coordinator { Coordinator(watcher: watcher) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = model.dataStore   // the same store the app reads ESPN's session from
        let view = WKWebView(frame: .zero, configuration: config)
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.load(URLRequest(url: Config.espnSignIn))
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        let watcher: EspnSignInWatcher
        init(watcher: EspnSignInWatcher) { self.watcher = watcher }

        func webView(_ webView: WKWebView, didCommit navigation: WKNavigation!) {
            let host = webView.url?.host ?? ""
            Task { @MainActor in watcher.host = host }
        }

        // ESPN's sign-in sometimes opens a second window; keep it in this one.
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if action.targetFrame == nil { webView.load(action.request) }
            return nil
        }
    }
}
