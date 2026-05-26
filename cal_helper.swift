// cal_helper.swift — Tiny EventKit helper for meeting_flyby.py
// Compiled once by meeting_flyby.py, then called as:
//     .cal_helper <minutes_ahead>
// Outputs one line per upcoming event:  Title||YYYY-MM-DD HH:MM

import EventKit
import Foundation

let minutes = CommandLine.arguments.count > 1
    ? (Double(CommandLine.arguments[1]) ?? 10)
    : 10.0

let store = EKEventStore()

// ── Request calendar access synchronously ──────────────────────
let sem = DispatchSemaphore(value: 0)
var ok = false

if #available(macOS 14.0, *) {
    store.requestFullAccessToEvents { granted, _ in
        ok = granted
        sem.signal()
    }
} else {
    store.requestAccess(to: .event) { granted, _ in
        ok = granted
        sem.signal()
    }
}
_ = sem.wait(timeout: .now() + 10)

guard ok else {
    fputs("NO_CALENDAR_ACCESS\n", stderr)
    exit(0)
}

// ── Query events in the next N minutes ─────────────────────────
let now = Date()
let later = Date(timeIntervalSinceNow: minutes * 60)
let pred = store.predicateForEvents(withStart: now, end: later, calendars: nil)
let events = store.events(matching: pred)

let fmt = DateFormatter()
fmt.dateFormat = "yyyy-MM-dd HH:mm"

for e in events {
    if e.isAllDay { continue }
    let t = (e.title ?? "Meeting")
        .replacingOccurrences(of: "||", with: " ")
        .replacingOccurrences(of: "\n", with: " ")
    print("\(t)||\(fmt.string(from: e.startDate))")
}
