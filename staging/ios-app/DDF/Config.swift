import Foundation

/// Where the app points. Release builds always load the DDF page; Debug builds can be pointed at the
/// local test harness with launch arguments (see README.md). Nothing here is a secret.
enum Config {
    static let productionPage = URL(string: "https://datadrivenfootball.github.io/ddf-staging/")!
    /// ESPN's own sign-in page. The app only shows it; it never reads what is typed into it.
    static let espnSignIn = URL(string: "https://www.espn.com/login")!

    static var page: URL {
        #if DEBUG
        if let text = UserDefaults.standard.string(forKey: "ddfBaseURL"), let url = URL(string: text) { return url }
        #endif
        return productionPage
    }

    /// Only this origin may ask the app for the ESPN session.
    static var pageOrigin: String { origin(of: page) }

    static func origin(of url: URL) -> String {
        guard let scheme = url.scheme, let host = url.host else { return "" }
        if let port = url.port { return "\(scheme)://\(host):\(port)" }
        return "\(scheme)://\(host)"
    }

    #if DEBUG
    /// `-ddfHarnessSignedIn YES`: the local harness treats the page as signed in to DDF.
    static var harnessSignedIn: Bool { UserDefaults.standard.bool(forKey: "ddfHarnessSignedIn") }
    /// `-ddfPlantTestESPN YES`: start with a fake ESPN session already in the cookie store.
    static var plantTestSession: Bool { UserDefaults.standard.bool(forKey: "ddfPlantTestESPN") }
    /// `-ddfTestSignInButton YES`: the ESPN sheet gets a "Test sign-in" button that plants the fake session,
    /// standing in for a real ESPN sign-in so the whole flow can run in the simulator.
    static var testSignInButton: Bool { UserDefaults.standard.bool(forKey: "ddfTestSignInButton") }
    #endif
}
