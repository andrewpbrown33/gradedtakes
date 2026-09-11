//  PageSchemeHandler.swift
//  GradedTakes
//
//  WKURLSchemeHandler for gradedtakes-pages://. Every request the web view
//  makes on that scheme comes here; the answer comes from PageService,
//  which decides between the network and the copy on disk.
//
//  WebKit rules this code follows (WKURLSchemeHandler docs):
//    - the protocol is @MainActor; every reply goes back on the main actor
//    - a task must receive a response, then data, then didFinish
//    - after `stop` is called for a task, touching it raises an ObjC
//      exception. Tasks are therefore tracked by identity and looked up
//      again after the await; a stopped task is simply dropped.

import Foundation
import WebKit

@MainActor
final class PageSchemeHandler: NSObject, WKURLSchemeHandler {
    private let service: PageService
    /// Tasks still owed a reply, by identity.
    private var pending: [ObjectIdentifier: any WKURLSchemeTask] = [:]

    init(service: PageService) {
        self.service = service
    }

    func webView(_ webView: WKWebView, start urlSchemeTask: any WKURLSchemeTask) {
        let id = ObjectIdentifier(urlSchemeTask)
        pending[id] = urlSchemeTask
        let request = urlSchemeTask.request

        guard let url = request.url, let path = PageScheme.path(from: url) else {
            finish(id, with: PageService.Reply(status: 404, mimeType: "text/plain", data: Data()), url: request.url)
            return
        }

        Task { @MainActor [weak self] in
            guard let self else { return }
            let reply = await self.service.serve(path: path)
            // `id` is an address. After `stop` releases a task, a new task
            // can be allocated at the same address while this serve is
            // still in flight - and would receive the OLD page's bytes.
            // Only the task this closure was started for is answered.
            guard self.pending[id] === urlSchemeTask else { return }
            self.finish(id, with: reply, url: url)
        }
    }

    func webView(_ webView: WKWebView, stop urlSchemeTask: any WKURLSchemeTask) {
        pending.removeValue(forKey: ObjectIdentifier(urlSchemeTask))
    }

    private func finish(_ id: ObjectIdentifier, with reply: PageService.Reply, url: URL?) {
        guard let task = pending.removeValue(forKey: id) else { return }   // stopped meanwhile
        let responseURL = url ?? PageScheme.url(for: PageScheme.homePath)
        let headers: [String: String] = [
            "Content-Type": reply.mimeType + (reply.mimeType.hasPrefix("text/") ? "; charset=utf-8" : ""),
            "Content-Length": String(reply.data.count),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        ]
        guard let response = HTTPURLResponse(url: responseURL, statusCode: reply.status, httpVersion: "HTTP/1.1", headerFields: headers) else {
            task.didFailWithError(URLError(.badServerResponse))
            return
        }
        task.didReceive(response)
        if !reply.data.isEmpty { task.didReceive(reply.data) }
        task.didFinish()
    }
}
