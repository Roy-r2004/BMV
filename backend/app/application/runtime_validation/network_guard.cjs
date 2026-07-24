"use strict";

const net = require("node:net");
const tls = require("node:tls");
const dns = require("node:dns");
const http = require("node:http");
const https = require("node:https");

const revision = "2026-07-24.1";
const loopbackNames = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

function hostnameOf(value) {
  if (typeof value === "string") {
    if (value.startsWith("/") || value.startsWith("\\\\.\\")) return "local-pipe";
    try {
      return new URL(value).hostname;
    } catch {
      return value;
    }
  }
  if (value && typeof value === "object") {
    return value.hostname || value.host || "localhost";
  }
  return "localhost";
}

function isLoopback(value) {
  const host = String(hostnameOf(value) || "").toLowerCase().replace(/^\[|\]$/g, "");
  return loopbackNames.has(host) || host.startsWith("127.");
}

function blocked(kind, target) {
  const diagnostic = JSON.stringify({
    code: "external_network_blocked",
    kind,
    target: String(hostnameOf(target)),
    revision,
  });
  process.stderr.write(`BMV_NETWORK_BLOCKED ${diagnostic}\n`);
  const error = new Error(`Phase 4 blocked external ${kind}`);
  error.code = "BMV_EXTERNAL_NETWORK_BLOCKED";
  throw error;
}

function connectTarget(args) {
  if (typeof args[0] === "number") {
    return typeof args[1] === "string" ? args[1] : "localhost";
  }
  return args[0];
}

function wrapConnect(original, kind) {
  return function guardedConnect(...args) {
    const target = connectTarget(args);
    if (!isLoopback(target)) blocked(kind, target);
    return original.apply(this, args);
  };
}

net.connect = wrapConnect(net.connect, "socket");
net.createConnection = wrapConnect(net.createConnection, "socket");
tls.connect = wrapConnect(tls.connect, "tls");

for (const method of ["lookup", "resolve", "resolve4", "resolve6"]) {
  const original = dns[method];
  if (!original) continue;
  dns[method] = function guardedDns(hostname, ...args) {
    if (!isLoopback(hostname)) blocked("dns", hostname);
    return original.call(this, hostname, ...args);
  };
}

for (const [module, kind] of [[http, "http"], [https, "https"]]) {
  for (const method of ["request", "get"]) {
    const original = module[method];
    module[method] = function guardedRequest(...args) {
      if (!isLoopback(args[0])) blocked(kind, args[0]);
      return original.apply(this, args);
    };
  }
}

globalThis.__BMV_NETWORK_GUARD__ = Object.freeze({
  installed: true,
  revision,
  loopbackOnly: true,
});
