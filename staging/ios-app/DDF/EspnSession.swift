import Foundation
import WebKit

/// ESPN's own session, as ESPN stores it for espn.com after a sign-in: the `espn_s2` and `SWID` cookies.
/// The app reads them from the web view's cookie store; it never sees the ESPN password.
struct EspnSession: Equatable {
    let espnS2: String
    let swid: String

    /// A signed-in ESPN session has both cookies, and a SWID in curly brackets. A visitor who has not
    /// signed in has no espn_s2.
    static func find(in cookies: [HTTPCookie]) -> EspnSession? {
        let espn = cookies.filter { ($0.domain == "espn.com" || $0.domain.hasSuffix(".espn.com")) && !$0.value.isEmpty }
        guard let s2 = espn.first(where: { $0.name == "espn_s2" })?.value else { return nil }
        // ESPN gives visitors a plain SWID too; the signed-in one is the one in curly brackets.
        let swids = espn.filter { $0.name == "SWID" }.map { $0.value.removingPercentEncoding ?? $0.value }
        guard let swid = swids.first(where: { $0.range(of: #"^\{[0-9A-Fa-f-]{36}\}$"#, options: .regularExpression) != nil }) else { return nil }
        return EspnSession(espnS2: s2, swid: swid)
    }

    @MainActor
    static func current(in store: WKHTTPCookieStore) async -> EspnSession? {
        find(in: await store.allCookies())
    }

    /// Signs the app's web views out of ESPN (used when the user disconnects ESPN in DDF).
    @MainActor
    static func forget(in store: WKHTTPCookieStore) async {
        for cookie in await store.allCookies() where cookie.domain == "espn.com" || cookie.domain.hasSuffix(".espn.com") {
            await store.deleteCookie(cookie)
        }
    }

    #if DEBUG
    /// A fake session the local harness accepts (espn_s2 starting "AEBtest" maps to a public league).
    @MainActor
    static func plantTestSession(in store: WKHTTPCookieStore) async {
        let values = ["espn_s2": "AEBtest" + String(repeating: "x", count: 80), "SWID": "{11111111-2222-3333-4444-555555555555}"]
        for (name, value) in values {
            let properties: [HTTPCookiePropertyKey: Any] = [.domain: ".espn.com", .path: "/", .name: name, .value: value, .secure: "TRUE", .expires: Date().addingTimeInterval(3600)]
            if let cookie = HTTPCookie(properties: properties) { await store.setCookie(cookie) } else { NSLog("DDF test cookie %@ could not be made", name) }
        }
    }
    #endif
}
