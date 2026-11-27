import SwiftUI
import WebKit

@main
struct DDFApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            PageScreen(model: model)
                .task { await model.start() }
                .onOpenURL { model.open($0) }
        }
    }
}

/// The DDF page, edge to edge under the status bar, in DDF's header green.
struct PageScreen: View {
    @ObservedObject var model: AppModel
    private let headerGreen = Color(red: 0.012, green: 0.271, blue: 0.192)   // --hdr #034531

    var body: some View {
        ZStack(alignment: .top) {
            PageWebView(view: model.pageView)
                .ignoresSafeArea(edges: .bottom)
            if let failed = model.pageFailed {
                VStack(spacing: 16) {
                    Text(failed).font(.headline).multilineTextAlignment(.center)
                    Button("Try again") { model.loadPage() }.buttonStyle(.borderedProminent).tint(Color(red: 0.09, green: 0.42, blue: 0.30))
                }
                .padding(32).frame(maxWidth: .infinity, maxHeight: .infinity).background(Color(red: 0.969, green: 0.973, blue: 0.961))
            }
        }
        .background(headerGreen.ignoresSafeArea(edges: .top))
        .preferredColorScheme(.light)
        .sheet(isPresented: $model.showingEspnSignIn) { EspnSignInSheet(model: model) }
    }
}

struct PageWebView: UIViewRepresentable {
    let view: WKWebView
    func makeUIView(context: Context) -> WKWebView { view }
    func updateUIView(_ view: WKWebView, context: Context) {}
}
