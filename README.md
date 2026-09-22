# 🏢 Learn APIs the School Way — the front office

The school method — proven on
[AWS](https://github.com/BaluRaut/learn-aws-school),
[Docker](https://github.com/BaluRaut/learn-docker-school),
[Kubernetes](https://github.com/BaluRaut/learn-kubernetes-school),
[MCP](https://github.com/BaluRaut/learn-mcp-school) and the rest of
[The School](https://baluraut.github.io/school/) — applied to **APIs**: how
programs talk to each other, taught as the school's **front office** — a slip at
the counter, a clerk, a stamped answer.

What makes this course different: **the counter is IN the repo.** A real HTTP/JSON
API in ~235 lines of pure Python, zero dependencies — you run it, curl it, break
it and extend it in every lesson.

🌐 **Interactive site:** **<https://baluraut.github.io/learn-api-school/>** —
lesson cards, every lesson as a numbered diagram, the big-picture 4K, a quiz, a
study plan and the before-and-trade-offs page. Lessons 13–16 are the full maps, each
drawn one type per row on the diagrams page:
**[every REST method](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l13)**,
**[every authentication method](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l14)**
(with every OAuth grant type),
**[every API type](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l15)** and
**[every kind of API test](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l16)**.

> 🎒 **Prerequisites:** Python 3 and curl. Nothing else. Good neighbours: the
> [Database school](https://github.com/BaluRaut/learn-database-school) (the record
> room behind this counter) and the [UI school](https://github.com/BaluRaut/learn-ui-school)
> (the notice board that calls it).

## 🚀 The 60-second wow

```bash
python3 api/school_api.py          # terminal 1: the front office opens on :8080
bash api/smoke_test.sh             # terminal 2: the whole course, in curl
```

Every stamp the course teaches, live: 200 + ETag, 404 with one error shape, 401
without a hall pass, 400 with field-level problems, 201 with an Idempotency-Key
(and the same answer on retry), cursor pages, 304 on an unchanged copy, 204 twice
for an idempotent delete, and 429 when the queue is full.

## 🗺️ The big picture

![The big picture: the counter (HTTP, REST, JSON, auth) and running it (errors, pagination, versioning, rate limits, beyond REST, testing and gateways)](docs/images/big-picture-4k.png)

## 🎓 The 16 lessons

Each numbered branch adds ONE lesson folder (`lessons/NN-topic/README.md`) with an
explain-like-I'm-5 story, a school analogy, a diagram, **What / Why / How**, a
hands-on lab on the real API, and Verify / Clean-up / Common-mistakes sections.
Branches are **sequential** — branch 07 contains lessons 01–07. Lessons 01–12 build
the counter; lessons 13–16 are **the full maps** — the reference lessons that place
everything else.

```bash
git checkout lesson-01-why-apis          # read lessons/01-why-apis/README.md, then...
git checkout lesson-02-http-anatomy      # ...keep going, one branch at a time
```

### Part 1 — the counter 📨

| # | Branch | You learn | Analogy |
|---|---|---|---|
| 01 | `lesson-01-why-apis` | Why a counter beats wandering into the archive; the contract | The front office 🏢 |
| 02 | `lesson-02-http-anatomy` | Method, path, headers, body; the four stamp families | The slip and the stamp 📨 |
| 03 | `lesson-03-rest-resources` | Nouns, collections, ids; safe and idempotent verbs | Filing cabinets 🗄️ |
| 04 | `lesson-04-json-and-schemas` | JSON, validation with field-level problems, OpenAPI | The standard form 📋 |
| 05 | `lesson-05-build-an-api` | Routes, checks, storage, plumbing — the four parts | Opening the counter 🔬 |
| 06 | `lesson-06-auth` | API keys, tokens, OAuth; 401 vs 403; least privilege | The hall pass 🪪 |

### Part 2 — running the counter 🏃

| # | Branch | You learn | Analogy |
|---|---|---|---|
| 07 | `lesson-07-errors-idempotency` | One error shape; retry rules; Idempotency-Key | Polite refusals, receipt numbers ⚠️🧾 |
| 08 | `lesson-08-pagination-filtering` | Filter → sort → paginate; cursors vs offsets | "The next 20, please" 📚 |
| 09 | `lesson-09-versioning` | Additive vs breaking; /v2; Deprecation and Sunset | New forms beside old 🔢 |
| 10 | `lesson-10-rate-limits-caching` | 429 + Retry-After, ETag/304, Cache-Control, timeouts, backoff | The queue and the copy ⏱️ |
| 11 | `lesson-11-beyond-rest` | GraphQL, gRPC, webhooks, events — the shape follows the caller | The counter calls you back 📣 |
| 12 | `lesson-12-testing-docs-gateway` | Contract tests, docs from the catalogue, request ids, the gateway | The school gate 🚪 |

### Part 3 — the full maps 🗺️

| # | Branch | You learn | Analogy |
|---|---|---|---|
| 13 | `lesson-13-rest-methods` | All seven methods — GET, HEAD, OPTIONS, POST, PUT, PATCH, DELETE — safe · idempotent · cacheable, the status codes each returns | The seven stamps 🔧 |
| 14 | `lesson-14-auth-methods` | Basic, API key, Bearer, JWT, cookie, OAuth 2.0 and every grant type, OpenID Connect, HMAC signing, mTLS; 401 vs 403 | Every hall pass 🪪 |
| 15 | `lesson-15-api-types` | Twenty API types in four families — REST to MQTT to batch files to system calls; six of them runnable | One school, many counters 🔀 |
| 16 | `lesson-16-testing-types` | Smoke, functional, integration, regression, load, stress, security, UI, fuzz — and the order to adopt them | Nine ways to test a counter 🧪 |

## 📦 What's in this repo (main branch)

```
learn-api-school/
├── api/
│   ├── school_api.py         # the front office: a REAL HTTP/JSON API, ~235 lines, zero deps
│   ├── smoke_test.sh         # the whole course as a curl script (contract test)
│   ├── openapi.yaml          # the printed catalogue of every form
│   ├── client.py             # the polite client: timeouts, backoff + jitter, ETag cache
│   ├── webhook_receiver.py   # where the counter calls you back
│   ├── api_types.py          # the SAME five students as REST · JSON-RPC · GraphQL · long polling · SSE · WebSocket
│   ├── types_client.py       # one client that exercises all six and prints every byte
│   ├── methods_demo.sh       # all SEVEN REST methods against the counter, with the headers that prove each rule
│   ├── auth_demo.py          # the same grades behind SEVEN auth schemes: Basic · API key · Bearer · JWT · HMAC · cookie · OAuth client_credentials
│   ├── auth_client.py        # every header on the wire, an expired token, a forged JWT, a replayed request
│   └── expected-output.txt   # what a healthy run prints
└── docs/                     # the GitHub Pages site
```

Everything runs on your laptop. **Cost: zero.**

## 🔀 Every API type

This course builds **one** API — a REST counter. The
[every API type](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l15) lesson is the
map of all the other shapes, in four families: **ask & answer** (REST, JSON-RPC, SOAP,
GraphQL, gRPC, tRPC, OData), **stay on the line** (long polling, SSE, WebSocket, WebRTC),
**leave a message** (webhooks, queues, event streams, batch files) and **no network at all**
(libraries, system calls, database drivers, device APIs) — with a master table, a decision
guide, and the mistakes that pick the wrong one.

Six of them run right here, against the same five students:

```bash
python3 api/api_types.py        # terminal 1 — :8081
python3 api/types_client.py     # terminal 2 — REST · JSON-RPC · GraphQL · long polling · SSE · WebSocket
```

## 🗺️ Part 3 — the full maps (lessons 13–16)

**Lesson 13.** The counter answers all seven methods — `PATCH` changes one field, `HEAD`
gives the headers only, `OPTIONS` lists what is allowed (and answers the browser's CORS
preflight). [Every REST method](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l13)
draws each one with the three words that tell them apart, the status codes it returns,
and a script that proves every rule:

```bash
python3 api/school_api.py        # terminal 1
bash api/methods_demo.sh         # terminal 2 — GET · HEAD · OPTIONS · POST · PUT · PATCH · DELETE
```

**Lesson 14.** [Every authentication method](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l14)
draws eleven flows — Basic, API key, Bearer token, JWT, session cookie, OAuth 2.0 with
PKCE, client credentials and device code, OpenID Connect, HMAC request signing, mutual
TLS — with every OAuth grant type, 401 vs 403 and the mistakes. Seven of them run here,
all guarding the same grades (the token endpoint refuses `grant_type=password`):

```bash
python3 api/auth_demo.py         # terminal 1 — :8082
python3 api/auth_client.py       # terminal 2 — every header, every 401 and 403
```

**Lesson 15.** [Every API type](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l15)
— twenty types in four families, from REST and gRPC to MQTT and batch files to the APIs
that never touch a network — with six of them runnable on the same five students:

```bash
python3 api/api_types.py         # terminal 1 — :8081
python3 api/types_client.py      # terminal 2 — REST · JSON-RPC · GraphQL · long polling · SSE · WebSocket
```

**Lesson 16.** [Every kind of API test](https://baluraut.github.io/learn-api-school/lesson-diagrams.html#l16)
— smoke, functional, integration, regression, load, stress, security, UI and fuzz, each
with how to run it against this counter, and the order to adopt them.

## 📜 License

MIT — see [LICENSE](LICENSE). Analogies are free to reuse; attribution appreciated.
