# DDF iOS app (prototype, JEG-1732)

> **On hold.** Jeremy, 2026-11-27, on shipping the app: "Website only for now." Kept as a prototype; nothing goes to TestFlight or the App Store until he reopens it.

A thin SwiftUI app around the DDF "Add your league" page. Its one job beyond showing the page: let a fan
connect a private ESPN league in three taps (Connect ESPN, sign in, pick league) without DDF ever seeing
the ESPN password.

## How it works
1. The page (`staging/account/app.js`) sees it is inside the app (`window.webkit.messageHandlers.ddfEspn`)
   and shows one button, **Connect ESPN**.
2. The button asks the app for an ESPN session. `AppModel` only answers DDF's own page, in the main frame.
3. If the app's web views are not signed in to ESPN, `EspnSignInSheet` shows ESPN's own sign-in page
   (`https://www.espn.com/login`). The user types into ESPN's page. The app reads nothing from the page;
   it watches the cookie store (`WKHTTPCookieStore`) and closes the sheet when ESPN's `espn_s2` and
   `SWID` cookies appear.
4. The app hands those two values to the page, which posts them to `POST /espn/session`. The server
   checks them with ESPN, seals them, and returns the leagues. One league: it is added at once. Several:
   the page lists them.
5. Already signed in to ESPN in the app: step 3 is skipped, so it is one tap.

Nothing is stored by the app itself. ESPN's cookies live in the web view's own store, as in a browser.
"Disconnect" for ESPN in the page also signs the app's web views out of ESPN.

## Files
- `DDF/Config.swift`: page URL, ESPN sign-in URL, debug switches.
- `DDF/AppModel.swift`: page web view, the `ddfEspn` request handler, link handling.
- `DDF/EspnSignInSheet.swift`: the ESPN sign-in sheet and the cookie watcher.
- `DDF/EspnSession.swift`: finds ESPN's session in the cookie store; debug test session.
- `Config/Info-Debug.plist` allows `http://localhost` (harness only). `Info-Release.plist` does not.

## Run it in the simulator
Needs Xcode 16 or later and a booted iOS 17+ simulator.

    ./run-sim.sh            # the real staging page
    ./run-sim.sh harness    # local harness, signed in to DDF, "Test sign-in" button on the ESPN sheet
    ./run-sim.sh planted    # local harness, already signed in to ESPN (one-tap path)

For the harness modes, start the JEG-1732 local harness first (it serves http://localhost:8791/ddf-staging/).
The debug switches are launch arguments (`-ddfBaseURL`, `-ddfHarnessSignedIn`, `-ddfPlantTestESPN`,
`-ddfTestSignInButton`) and are compiled out of Release builds.

## Not done yet
- No app icon, no launch artwork.
- DDF sign-in inside the app: the emailed link must open the app. The app handles `ddf://signin#…` and the
  page asks for that redirect when it runs in the app, but `ddf://signin` is not yet in Supabase's allowed
  redirect list, and this was not tested against Supabase. Google sign-in does not work inside a web view
  (Google blocks it) and needs the system sign-in sheet.
- The page keeps the DDF session only while the app is open (sessionStorage).
- A real ESPN sign-in has not been completed in the app (no test ESPN account was used).
