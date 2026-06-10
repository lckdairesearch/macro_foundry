# Proposal — Frontend-Safe API Boundary

**Status:** Draft proposal

**Date:** 2026-06-08

## Why this exists

The current `macro_foundry` API is an internal backend skeleton for a trusted,
single-user phase. It uses one shared bearer token across the API surface and
exposes broad table-oriented CRUD routes. That is acceptable for local/admin
use, but it is not a safe browser-facing interface.

If a frontend ships the current bearer token to the browser, the token becomes
the user's token. At that point the user can call the API directly outside the
UI and reach whatever the token authorizes.

The risk is not "someone guessed the table name." The risk is:

- the browser holds a shared secret
- the current routes are generic and broad
- the current route shapes mirror internal tables rather than UI-specific views

## Core recommendation

Do **not** expose the current `/api/v1` surface directly to a browser-based
frontend.

Instead, keep the current API private/internal and add a second, narrower
service boundary for frontend consumption.

## Proposed next-step architecture

```text
Browser / frontend UI
        |
        | user auth session or signed cookie
        v
Frontend backend / BFF
        |
        | service-to-service auth
        v
macro_foundry internal API
        |
        v
Postgres
```

### Responsibilities by layer

**Browser / frontend UI**

- renders charts, tables, and search results
- never stores the internal `macro_foundry` bearer token
- only calls frontend-safe endpoints

**Frontend backend / BFF**

- authenticates the end user
- decides which consolidated payloads the UI may read
- calls internal `macro_foundry` endpoints using server-side credentials
- applies rate limits, caching, and any product-specific access policy
- returns UI-shaped read models instead of raw table rows

**macro_foundry internal API**

- remains the system-of-record API over the canonical schema
- continues serving admin, operators, trusted agents, and ingestion workflows
- is not exposed directly to the public internet for browser use

## Important security clarification

If data is sent to the browser, the browser user can read that data. There is
no way around that.

The goal is therefore **not** "hide the data after it reaches the browser." The
goal is:

- do not ship internal credentials to the browser
- do not expose generic table CRUD to the browser
- expose only the minimum consolidated payload required for the product surface

## API split

### Internal surface

Keep the current table-oriented routes as an internal/operator API.

Candidate characteristics:

- private network only, or at minimum not linked from the public app
- separate credentials from end-user auth
- SQLAdmin stays internal
- OpenAPI docs stay internal or are disabled in production

### Frontend-safe surface

Add a purpose-built read API for UI consumption.

Recommended characteristics:

- read-only at first
- resource-oriented around product use cases, not tables
- stable payloads shaped for charts, tables, summaries, and search
- no arbitrary access to every model field

Example endpoint families:

- `/app/v1/dashboard/home`
- `/app/v1/series/{series_code}/chart`
- `/app/v1/series/{series_code}/summary`
- `/app/v1/search`
- `/app/v1/countries/{geography_code}/overview`

These endpoints should return consolidated read models such as:

- resolved series metadata plus latest observations
- chart-ready time series arrays
- grouped dashboard cards
- curated search results

They should **not** return raw joins over internal tables just because the UI
happens to need those fields today.

## Authentication and authorization

Use three distinct auth contexts.

### 1. Admin auth

- for SQLAdmin only
- current username/password session model is fine for internal admin use

### 2. Internal service auth

- used by the frontend backend when it calls `macro_foundry`
- separate from browser auth
- can remain a bearer token initially, but it should be server-side only

### 3. End-user auth

- used by the browser to authenticate to the frontend backend
- session/cookie or equivalent user-level auth
- never reused as direct database or internal API credentials

## Deployment posture

For a real frontend deployment, the default posture should be:

- `macro_foundry` API: internal/private
- SQLAdmin: internal/private
- frontend backend: public
- browser: public

If `macro_foundry` remains internet-reachable, treat that as an exception that
requires compensating controls rather than the default deployment model.

## Suggested implementation phases

### Phase A — Contain the current surface

- treat `/api/v1` and `/admin` as internal-only
- do not embed the current API bearer token in frontend code
- plan to disable or hide `/docs` in production

### Phase B — Introduce frontend-safe read models

- identify the first 2-3 actual UI screens
- define one endpoint per screen or per coherent UI capability
- return consolidated payloads instead of raw CRUD resources

### Phase C — Add a frontend backend / BFF

- authenticate end users there
- call `macro_foundry` server-to-server
- add caching for expensive reads and common dashboard payloads

### Phase D — Revisit writes later

- if the product later allows user-triggered writes, expose narrowly scoped
  commands rather than generic table mutation endpoints

## Recommended first slice

If the immediate goal is "show consolidated macro data in a frontend", the
first safe slice is:

1. keep current `macro_foundry` routes private
2. add one frontend backend
3. implement one read-only dashboard endpoint backed by a curated query
4. implement one read-only series-detail endpoint backed by a curated query

That is enough to prove the architecture without turning the internal CRUD layer
into a public contract.

## Open questions before implementation

- Will the first frontend be private-to-you, shared with a small team, or
  public internet-facing?
- Is the first product surface mostly dashboard/search reads, or does it need
  authenticated write actions early?
- Should the frontend backend live inside this repo, or as a separate app that
  consumes `macro_foundry` as an internal service?

## Non-goals of this proposal

- replacing the current internal CRUD layer
- redesigning the canonical schema
- choosing a specific end-user auth vendor
- defining a full public API product contract

## Bottom line

The current API is an internal data/admin surface, not a browser-safe product
API. The next step is not "make the frontend call the current routes more
carefully." The next step is to introduce a narrower frontend-safe boundary and
keep the current CRUD/admin surface private.
