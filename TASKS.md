# SensFlow V1 Implementation Roadmap

Status: Planning only  
Scope: SensFlow Version 1  
Task size: 30–90 minutes of focused implementation time

## Roadmap rules

- Follow the document precedence defined in `docs/00_INDEX.md`: `BUSINESS_RULES`, `PROJECT_REQUIREMENTS`, `ALGORITHMS`, `ARCHITECTURE`, `DATABASE`, then the remaining documents.
- Complete milestones in the order defined by `docs/09_IMPLEMENTATION_PLAN.md`. Do not start a later milestone until the current milestone exit gate is complete.
- Treat the pre-implementation gate below as clarification work, not as an additional product phase.
- Keep every code change small enough to review independently. A task that grows beyond 90 minutes must be split before implementation continues.
- Include tests in the task that introduces behavior. Milestone 9 expands and validates the complete test suite; it does not postpone testing until the end.
- Do not add undocumented product features. Internal reliability mechanisms may be added only when they enforce documented correctness, recovery, security, or observability requirements.
- Do not silently resolve a specification conflict. Record the decision and obtain approval before implementing the affected behavior.
- Preserve business history, prevent duplicate Marketplace Orders and purchases, and keep completed orders and finalized financial values immutable.

## Pre-implementation clarification gate

These tasks must be completed before Phase 1 exits. Any resolution that changes an authoritative requirement must be approved and reflected in the appropriate source document before dependent implementation begins.

### PRE-01 — Approve canonical order terminology and state transitions (60 min)

Completion checklist:

- [ ] Define whether “Active Order” is an alias for `Purchasing` and approve one canonical term.
- [ ] Approve every allowed transition among Draft, PreOrder, Purchasing, Completed, and Cancelled.
- [ ] Define deletion and cancellation behavior for Draft, Purchasing, and Completed orders.

### PRE-02 — Approve marketplace execution and partial-fill rules (90 min)

Completion checklist:

- [ ] Define active, pending, cancelling, cancelled, partial, completed, and failed Marketplace Order semantics.
- [ ] Define the quantity used for replacement orders after partial execution.
- [ ] Resolve the “exactly one active order” requirement during cancel-and-recreate gaps.

### PRE-03 — Obtain and approve external API contracts (90 min)

Completion checklist:

- [ ] Record RBXCreate authentication, endpoints, schemas, status mapping, errors, limits, and idempotency capabilities.
- [ ] Record Roblox identity and Place ID discovery endpoints and selection rules.
- [ ] Identify sandbox, fixture, or fake-server data that can be used without production activity.

### PRE-04 — Approve financial formulas and numeric policies (60 min)

Completion checklist:

- [ ] Define Requested Robux, Customer Receives, marketplace-rate units, and Roblox tax behavior.
- [ ] Define cost, commission, currency-conversion formulas, currency code, precision, and rounding.
- [ ] Define when rate, commission, and exchange-rate settings are captured for historical orders.

### PRE-05 — Approve scheduling and stock-allocation rules (90 min)

Completion checklist:

- [ ] Define deterministic tie-breaking for the Maximum Customers strategy.
- [ ] Define stock buckets, reservations, partial allocation, and concurrent payment-confirmation behavior.
- [ ] Resolve how newly paid orders compete with existing PreOrders without bypassing the scheduling objective.

### PRE-06 — Approve runtime and configuration boundaries (60 min)

Completion checklist:

- [ ] Decide whether the bot and background workers run in one process or separate services.
- [ ] Define the V1 roles of FastAPI, Redis, and the required Stock Cache.
- [ ] Add synchronization interval and notification-category behavior to the approved settings contract.

## Milestone 1 — Project foundation

Corresponds to Phase 1 in `IMPLEMENTATION_PLAN.md`.

### FND-01 — Initialize Python and dependency metadata (45 min)

Completion checklist:

- [ ] Configure Python 3.13 and `uv` project metadata with only the approved stack.
- [ ] Separate runtime, development, and test dependencies.
- [ ] Verify a clean dependency sync succeeds.

### FND-02 — Create the layered package skeleton (45 min)

Completion checklist:

- [ ] Create Telegram, application, domain, repository, integration, and infrastructure package boundaries.
- [ ] Add empty module exports only where they clarify public interfaces.
- [ ] Verify imports do not create circular dependencies.

### FND-03 — Implement environment configuration loading (75 min)

Completion checklist:

- [ ] Define typed Pydantic settings for database, Telegram, marketplace, automation, finance, and logging configuration.
- [ ] Reject missing or invalid mandatory configuration with clear startup errors.
- [ ] Add unit tests for valid, missing, and malformed configuration.

### FND-04 — Implement secret-safe configuration handling (45 min)

Completion checklist:

- [ ] Mark Telegram, RBXCreate, Roblox, and database credentials as secrets.
- [ ] Ensure configuration representations and validation errors cannot expose secret values.
- [ ] Add a redaction regression test.

### FND-05 — Configure structured application logging (60 min)

Completion checklist:

- [ ] Produce structured logs with level, module, timestamp, and correlation context.
- [ ] Redact authentication headers, tokens, credentials, and sensitive request content.
- [ ] Verify logging failure does not mutate business state.

### FND-06 — Define dependency-injection and unit-of-work contracts (60 min)

Completion checklist:

- [ ] Define composition boundaries for repositories, external clients, settings, clock, and notifications.
- [ ] Define commit, rollback, and context-lifetime behavior without business logic.
- [ ] Add lightweight contract tests using fakes.

### FND-07 — Create the application container image (60 min)

Completion checklist:

- [ ] Add a minimal non-root Python 3.13 image with deterministic dependency installation.
- [ ] Configure a graceful application entry point.
- [ ] Verify the image builds without embedding secrets.

### FND-08 — Create the development Docker Compose topology (75 min)

Completion checklist:

- [ ] Configure the application, PostgreSQL 17, persistent storage, and approved Redis topology.
- [ ] Add health checks and explicit service dependencies.
- [ ] Verify data persists across container recreation.

### FND-09 — Configure linting and the test harness (45 min)

Completion checklist:

- [ ] Configure Ruff and pytest with deterministic defaults.
- [ ] Add unit and integration test markers and shared fixture boundaries.
- [ ] Verify linting and an empty smoke suite run successfully.

### FND-10 — Phase 1 exit gate (30 min)

Completion checklist:

- [ ] Run dependency, import, configuration, lint, test, image-build, and Compose smoke checks.
- [ ] Confirm every PRE task affecting foundation decisions is approved.
- [ ] Record that the project skeleton starts, stops, and fails safely.

## Milestone 2 — Database and repositories

Corresponds to Phase 2 in `IMPLEMENTATION_PLAN.md`.

### DB-01 — Configure SQLAlchemy engine and sessions (60 min)

Completion checklist:

- [ ] Configure async PostgreSQL engine, session factory, transaction scope, and connection validation.
- [ ] Ensure sessions always close and failed transactions roll back.
- [ ] Add connection and rollback integration tests.

### DB-02 — Define shared database conventions (45 min)

Completion checklist:

- [ ] Define UUID primary keys, UTC timestamps, naming conventions, and enum storage policy.
- [ ] Define integer Robux and fixed-precision monetary column conventions.
- [ ] Test UUID and timestamp defaults.

### DB-03 — Implement the Customer schema (75 min)

Completion checklist:

- [ ] Add all required Customer fields and the unique Roblox User ID constraint.
- [ ] Enforce non-empty current username and archived-not-deleted behavior.
- [ ] Add schema and constraint tests.

### DB-04 — Implement username and Place ID history storage (75 min)

Completion checklist:

- [ ] Store username and Place ID history as append-only Customer-owned records or equivalent physical storage.
- [ ] Preserve chronological change metadata without creating new product-level entities.
- [ ] Test that history cannot be silently overwritten or deleted.

### DB-05 — Implement the ClientOrder schema (90 min)

Completion checklist:

- [ ] Add Customer reference, status, Robux, Place ID, rate-limit, financial, and lifecycle timestamp fields.
- [ ] Enforce referential integrity and valid positive quantities.
- [ ] Add schema tests for Draft, terminal, and financial-nullability cases.

### DB-06 — Implement the MarketplaceOrder schema (75 min)

Completion checklist:

- [ ] Add ClientOrder reference, external ID, status, rate, requested, purchased, remaining, and lifecycle timestamps.
- [ ] Preserve historical attempts after cancellation or completion.
- [ ] Add amount-consistency and referential-integrity tests.

### DB-07 — Enforce the single-active-Marketplace-Order invariant (60 min)

Completion checklist:

- [ ] Add a database constraint or partial unique index for one active attempt per Client Order.
- [ ] Define the approved active-status set in one location.
- [ ] Prove concurrent inserts cannot create two active attempts.

### DB-08 — Implement the TimelineEvent schema (60 min)

Completion checklist:

- [ ] Add required event type, description, ClientOrder reference, UUID, and UTC creation time.
- [ ] Prevent update and delete through the repository contract.
- [ ] Test chronological retrieval and append-only behavior.

### DB-09 — Implement the SystemSettings schema (75 min)

Completion checklist:

- [ ] Store every approved marketplace, automation, finance, notification, synchronization, and timezone setting.
- [ ] Enforce exactly one active configuration while preserving any required history.
- [ ] Add persistence and valid-range tests.

### DB-10 — Implement the Notification schema (60 min)

Completion checklist:

- [ ] Add optional ClientOrder relation, category, content, delivery state, attempts, and timestamps required by the approved contract.
- [ ] Preserve failed and delivered notification history.
- [ ] Add state-transition and retrieval tests.

### DB-11 — Implement the Statistics schema (75 min)

Completion checklist:

- [ ] Implement the approved logical representation for totals and period-based statistics.
- [ ] Add uniqueness rules preventing duplicate period projections.
- [ ] Verify statistics can be rebuilt from Completed orders.

### DB-12 — Implement the SystemLog schema (60 min)

Completion checklist:

- [ ] Add UUID, level, module, message, related entity, and UTC creation time.
- [ ] Keep the repository append-only and independent from business success.
- [ ] Add log insertion and failure-isolation tests.

### DB-13 — Create the initial Alembic migration (90 min)

Completion checklist:

- [ ] Generate and review a migration containing all approved entities, constraints, and indexes.
- [ ] Verify upgrade on an empty PostgreSQL database.
- [ ] Verify downgrade and repeatable re-upgrade in development.

### DB-14 — Implement the Customer repository (75 min)

Completion checklist:

- [ ] Support lookup by UUID, Roblox User ID, username, archive state, and search criteria.
- [ ] Support atomic Customer and history updates.
- [ ] Add repository integration tests including duplicate prevention.

### DB-15 — Implement the ClientOrder repository (90 min)

Completion checklist:

- [ ] Support status lists, search, locked retrieval, save, and permitted Draft deletion semantics.
- [ ] Prevent repository operations from modifying Completed orders.
- [ ] Add concurrent-lock and immutable-order tests.

### DB-16 — Implement the MarketplaceOrder repository (75 min)

Completion checklist:

- [ ] Support active-attempt lookup, external-ID lookup, history, and status updates.
- [ ] Expose operations needed for synchronization and reorder without embedding business rules.
- [ ] Add active-attempt and history tests.

### DB-17 — Implement supporting repositories (90 min)

Completion checklist:

- [ ] Implement repositories for TimelineEvent, SystemSettings, Notification, Statistics, and SystemLog.
- [ ] Preserve append-only and singleton/period constraints.
- [ ] Add integration tests for each public repository operation.

### DB-18 — Phase 2 exit gate (45 min)

Completion checklist:

- [ ] Run migrations and the complete database integration suite on a clean database.
- [ ] Verify uniqueness, foreign keys, immutability, UTC storage, and restart persistence.
- [ ] Confirm no repository contains business decisions.

## Milestone 3 — Telegram bot

Corresponds to Phase 3 in `IMPLEMENTATION_PLAN.md`. Use application interfaces and fakes until Milestone 4 supplies real business services.

### BOT-01 — Bootstrap aiogram and operator authorization (75 min)

Completion checklist:

- [ ] Initialize the bot, dispatcher, routers, and configured single-operator allowlist.
- [ ] Deny unauthorized updates without exposing business information.
- [ ] Add authorized and unauthorized update tests.

### BOT-02 — Implement shared navigation components (75 min)

Completion checklist:

- [ ] Implement consistent Home, Back, Refresh, and Close behavior.
- [ ] Define compact, validated callback-data structures.
- [ ] Add navigation and stale-callback tests.

### BOT-03 — Implement the Main Menu and System Status screen (60 min)

Completion checklist:

- [ ] Add Create Order, Orders, Customers, Statistics, Settings, and System Status entries.
- [ ] Render operator-focused service availability without credentials or sensitive details.
- [ ] Add menu rendering and callback-routing tests.

### BOT-04 — Implement the Create Order conversation shell (90 min)

Completion checklist:

- [ ] Collect username and Requested Robux through an aiogram state flow.
- [ ] Support discovered Place ID confirmation and manual fallback presentation.
- [ ] Validate input presentation while delegating all business validation to an application interface.

### BOT-05 — Implement status-grouped order lists (75 min)

Completion checklist:

- [ ] Render Draft, PreOrder, Purchasing, Completed, and Cancelled counts and lists.
- [ ] Add stable pagination and empty-state behavior.
- [ ] Test every status and page boundary.

### BOT-06 — Implement the Order Details screen (75 min)

Completion checklist:

- [ ] Render all fields required by `TELEGRAM_UI.md`, including timeline and financial values when available.
- [ ] Hide actions that are invalid for the current state without duplicating transition rules.
- [ ] Test Draft, Purchasing, Completed, and Cancelled rendering.

### BOT-07 — Implement order action callbacks (75 min)

Completion checklist:

- [ ] Add Confirm Payment, Manual Reorder, Cancel, Refresh, and View Timeline callbacks.
- [ ] Prevent duplicate submissions and display business errors consistently.
- [ ] Add callback delegation tests using fake use cases.

### BOT-08 — Implement Customer search and details screens (75 min)

Completion checklist:

- [ ] Support search and display username, Roblox User ID, current Place ID, histories, orders, and notes.
- [ ] Add pagination for histories and order lists.
- [ ] Test not-found, archived, and multi-page cases.

### BOT-09 — Implement Customer action callbacks (60 min)

Completion checklist:

- [ ] Add Refresh Information, Update Place ID, and Archive actions.
- [ ] Delegate changes to application interfaces and show approved results.
- [ ] Add invalid-place and archived-customer presentation tests.

### BOT-10 — Implement Settings screens (90 min)

Completion checklist:

- [ ] Render and edit every approved V1 setting and notification category.
- [ ] Confirm parsed values without exposing credentials.
- [ ] Add navigation, validation-message, and refresh tests.

### BOT-11 — Implement Statistics screens (60 min)

Completion checklist:

- [ ] Render documented order, Robux, rate, commission, and spending metrics.
- [ ] Support approved daily, weekly, and monthly views.
- [ ] Add empty and populated rendering tests.

### BOT-12 — Implement the Telegram notification adapter (60 min)

Completion checklist:

- [ ] Implement delivery for every approved notification category.
- [ ] Return typed success, retryable failure, and permanent failure results.
- [ ] Test content escaping and transport failures.

### BOT-13 — Add shared Telegram error and pagination behavior (60 min)

Completion checklist:

- [ ] Map validation, not-found, conflict, unavailable, and unexpected errors to safe operator messages.
- [ ] Keep callback answers responsive during longer use cases.
- [ ] Add malformed-update and oversized-list tests.

### BOT-14 — Phase 3 exit gate (45 min)

Completion checklist:

- [ ] Run the Telegram component suite with fake application services.
- [ ] Verify every documented screen, navigation action, and operator workflow is reachable.
- [ ] Confirm handlers contain presentation logic only.

## Milestone 4 — Business logic

Corresponds to Phase 4 in `IMPLEMENTATION_PLAN.md`.

### BIZ-01 — Define domain value objects and business errors (75 min)

Completion checklist:

- [ ] Define typed IDs, statuses, Robux quantities, rates, money, and approved business error categories.
- [ ] Enforce numeric and state-independent invariants at construction time.
- [ ] Add focused unit tests for valid and invalid values.

### BIZ-02 — Implement Customer identity resolution (90 min)

Completion checklist:

- [ ] Resolve Roblox User ID before determining Customer uniqueness.
- [ ] Return an existing Customer or create exactly one new Customer atomically.
- [ ] Test username changes, duplicate requests, and failed Roblox lookup.

### BIZ-03 — Implement Customer username refresh and history (60 min)

Completion checklist:

- [ ] Update current username only when the verified Roblox identity matches.
- [ ] Append the prior username exactly once.
- [ ] Test unchanged, changed, repeated, and failed refreshes.

### BIZ-04 — Implement Place ID discovery and update workflow (90 min)

Completion checklist:

- [ ] Use stored Place ID, automatic discovery, and manual fallback in the approved order.
- [ ] Append previous Place IDs when an update succeeds.
- [ ] Test discovery failure, invalid manual input, and order snapshot behavior.

### BIZ-05 — Implement Draft creation (75 min)

Completion checklist:

- [ ] Create a Draft only for a valid Customer, positive Requested Robux, and valid Place ID.
- [ ] Capture required order values and append Order Created to the timeline atomically.
- [ ] Test rollback and duplicate-submission behavior.

### BIZ-06 — Implement Draft editing and deletion semantics (75 min)

Completion checklist:

- [ ] Permit edits only while the order remains Draft.
- [ ] Implement the approved soft-delete or physical-delete rule without violating history requirements.
- [ ] Test edits and deletion attempts in every order state.

### BIZ-07 — Implement the ClientOrder state machine (90 min)

Completion checklist:

- [ ] Encode every approved transition and terminal-state rule in one domain component.
- [ ] Reject invalid and repeated transitions deterministically.
- [ ] Add a transition-matrix unit test covering all state pairs.

### BIZ-08 — Implement payment confirmation orchestration (90 min)

Completion checklist:

- [ ] Confirm payment exactly once and evaluate approved available-stock semantics.
- [ ] Route atomically to Purchasing or PreOrder without operator override.
- [ ] Add concurrency, retry, no-stock, and eligible-stock tests.

### BIZ-09 — Implement PreOrder and Purchasing entry behavior (75 min)

Completion checklist:

- [ ] Append the required timeline events for both branches.
- [ ] Create a marketplace-execution intent only for Purchasing orders.
- [ ] Test that Draft, Cancelled, and Completed orders cannot obtain an intent.

### BIZ-10 — Implement ClientOrder cancellation (90 min)

Completion checklist:

- [ ] Cancel only approved non-terminal states and coordinate external cancellation when required.
- [ ] Preserve all history and stop future scheduling or automation.
- [ ] Test idempotent, active-marketplace, and Completed-order cases.

### BIZ-11 — Implement MarketplaceOrder domain policies (75 min)

Completion checklist:

- [ ] Validate attempt creation, status updates, purchased quantity, and remaining quantity.
- [ ] Enforce at most one active attempt without deleting earlier attempts.
- [ ] Test partial, cancelled, replacement, and completed histories.

### BIZ-12 — Implement timeline event creation (60 min)

Completion checklist:

- [ ] Provide one application-facing path for every required timeline event.
- [ ] Generate events in the same transaction as the related business change.
- [ ] Test event type, order, description, and duplicate prevention.

### BIZ-13 — Implement Robux and tax calculations (60 min)

Completion checklist:

- [ ] Calculate Customer Receives using the approved Roblox rule and rounding policy.
- [ ] Store Robux values as integers and reject impossible quantities.
- [ ] Add boundary and rounding tests.

### BIZ-14 — Implement marketplace cost and currency calculations (75 min)

Completion checklist:

- [ ] Calculate Marketplace Cost, commission, Final Cost USD, and Final Cost Local Currency with Decimal arithmetic.
- [ ] Capture the approved settings snapshots used by the calculation.
- [ ] Add formula, precision, and historical-stability tests.

### BIZ-15 — Implement purchase completion orchestration (90 min)

Completion checklist:

- [ ] Validate marketplace confirmation and finalize order, attempt, finance, timeline, statistics input, and notification intent atomically.
- [ ] Make repeated completion reports idempotent.
- [ ] Test rollback at each validation failure and Completed-order immutability.

### BIZ-16 — Implement Settings service (75 min)

Completion checklist:

- [ ] Validate and persist every approved setting through one service.
- [ ] Apply changes only to operations considered future by the approved policy.
- [ ] Add invalid-range, persistence, and historical-value tests.

### BIZ-17 — Wire Customer and order Telegram workflows (90 min)

Completion checklist:

- [ ] Replace Customer, Draft, payment, cancellation, refresh, and details fakes with real application use cases.
- [ ] Keep handlers free of repository and business-rule access.
- [ ] Add Telegram-to-application integration tests.

### BIZ-18 — Wire Settings and order-action Telegram workflows (75 min)

Completion checklist:

- [ ] Connect Settings, Manual Reorder request, archive, and Place ID update screens to application use cases.
- [ ] Render conflict and validation outcomes consistently.
- [ ] Add integration tests for each operator action.

### BIZ-19 — Add business-service authorization enforcement (45 min)

Completion checklist:

- [ ] Require an authorized operator context for every mutating application use case.
- [ ] Ensure transport-level authorization cannot be the only protection.
- [ ] Add unauthorized-use-case tests.

### BIZ-20 — Phase 4 exit gate (45 min)

Completion checklist:

- [ ] Run domain, application, repository, and Telegram integration suites.
- [ ] Verify all Customer and ClientOrder business rules and timeline requirements.
- [ ] Confirm external marketplaces remain behind interfaces and no production call is required.

## Milestone 5 — RBXCreate and Roblox integration

Corresponds to Phase 5 in `IMPLEMENTATION_PLAN.md`.

### API-01 — Implement the shared HTTP transport policy (75 min)

Completion checklist:

- [ ] Configure timeouts, connection limits, correlation IDs, redacted logging, and response-size safeguards.
- [ ] Return typed transport errors without modifying business entities.
- [ ] Add timeout, disconnect, malformed-response, and redaction tests.

### API-02 — Implement RBXCreate authentication (60 min)

Completion checklist:

- [ ] Apply the approved authentication method to every marketplace request.
- [ ] Classify authentication failure as a marketplace-stopping condition.
- [ ] Verify credentials never appear in logs or exceptions.

### API-03 — Implement marketplace stock retrieval (75 min)

Completion checklist:

- [ ] Map approved stock responses into validated rate, Robux, availability, and retrieval-time values.
- [ ] Reject incomplete, negative, stale, or unexpected stock data.
- [ ] Add contract fixtures for eligible, ineligible, empty, and invalid stock.

### API-04 — Implement Marketplace Order creation (90 min)

Completion checklist:

- [ ] Send approved Place ID, remaining quantity, rate limit, and idempotency/correlation data.
- [ ] Validate the returned external order identifier and initial status.
- [ ] Add success, duplicate-response, timeout, and invalid-response tests.

### API-05 — Implement Marketplace Order retrieval (75 min)

Completion checklist:

- [ ] Retrieve an order by approved external identifier.
- [ ] Map quantities and status without performing ClientOrder transitions in the adapter.
- [ ] Add not-found, partial, completed, cancelled, and unknown-status tests.

### API-06 — Implement Marketplace Order cancellation (75 min)

Completion checklist:

- [ ] Send cancellation using the approved contract and validate confirmation.
- [ ] Distinguish already-completed, already-cancelled, retryable, and permanent outcomes.
- [ ] Add race-condition response fixtures.

### API-07 — Implement marketplace status mapping and validation (60 min)

Completion checklist:

- [ ] Map every approved RBXCreate status to an internal integration status.
- [ ] Reject unknown statuses without mutating business data.
- [ ] Add an exhaustive mapping test.

### API-08 — Implement retry and rate-limit behavior (75 min)

Completion checklist:

- [ ] Retry only approved temporary failures with bounded exponential backoff and jitter.
- [ ] Respect rate-limit and retry-after information.
- [ ] Test attempt limits and permanent-failure termination without real waiting.

### API-09 — Implement create-operation reconciliation (90 min)

Completion checklist:

- [ ] Reconcile a timed-out or interrupted create request using approved idempotency or lookup capabilities.
- [ ] Prevent a retry from creating a second Marketplace Order.
- [ ] Add crash-window and ambiguous-response tests.

### API-10 — Implement Roblox user identity lookup (75 min)

Completion checklist:

- [ ] Resolve username to permanent Roblox User ID and current username.
- [ ] Validate not-found, renamed, malformed, and unavailable responses.
- [ ] Add contract fixtures without production calls.

### API-11 — Implement Roblox Place ID discovery (90 min)

Completion checklist:

- [ ] Apply the approved selection algorithm when a Roblox account has zero, one, or multiple candidate places.
- [ ] Validate Place IDs before returning them to application services.
- [ ] Add discovery, ambiguity, and manual-fallback tests.

### API-12 — Build RBXCreate fake-server contract tests (90 min)

Completion checklist:

- [ ] Cover authentication, stock, create, retrieve, cancel, rate limits, invalid data, and timeouts.
- [ ] Assert requests match the approved API contract exactly.
- [ ] Verify no test contacts the production marketplace.

### API-13 — Build Roblox fake-server contract tests (60 min)

Completion checklist:

- [ ] Cover identity lookup, username changes, Place ID discovery, invalid data, and outages.
- [ ] Assert request and response mappings against the approved contract.
- [ ] Verify no test contacts production Roblox services.

### API-14 — Phase 5 exit gate (45 min)

Completion checklist:

- [ ] Run all adapter and fake-server contract suites.
- [ ] Verify external failures cannot commit business-state changes.
- [ ] Confirm credentials are configurable, redacted, and replaceable without reinstalling the application.

## Milestone 6 — Automation

Corresponds to Phase 6 in `IMPLEMENTATION_PLAN.md`.

### AUT-01 — Implement background-service lifecycle control (75 min)

Completion checklist:

- [ ] Start, stop, cancel, and supervise monitoring, synchronization, reorder, recovery, and notification jobs.
- [ ] Prevent one job failure from silently stopping unrelated jobs.
- [ ] Add lifecycle and graceful-cancellation tests.

### AUT-02 — Implement the approved Stock Cache (75 min)

Completion checklist:

- [ ] Store validated stock, retrieval time, expiry, and rate context in the approved backend.
- [ ] Prevent stale or malformed snapshots from driving purchases.
- [ ] Add expiry, replacement, and restart-behavior tests.

### AUT-03 — Implement continuous stock monitoring (75 min)

Completion checklist:

- [ ] Poll at the configurable interval and update the Stock Cache only after validation.
- [ ] Trigger scheduling when newly eligible stock appears.
- [ ] Add interval-change, outage, recovery, and shutdown tests.

### AUT-04 — Implement scheduler candidate loading (60 min)

Completion checklist:

- [ ] Load only eligible PreOrders with all approved scheduling inputs.
- [ ] Exclude Draft, Purchasing, Completed, Cancelled, archived, or already-reserved work as approved.
- [ ] Add eligibility boundary tests.

### AUT-05 — Implement the Maximum Customers algorithm (90 min)

Completion checklist:

- [ ] Select a feasible combination completing the greatest number of customers.
- [ ] Apply the approved deterministic secondary tie-break rules.
- [ ] Add documented-example, empty, exact-fit, insufficient-stock, and tie tests.

### AUT-06 — Add scheduler property and determinism tests (75 min)

Completion checklist:

- [ ] Compare optimized results with a brute-force oracle for bounded random inputs.
- [ ] Prove identical inputs always produce identical selections.
- [ ] Verify selected quantity never exceeds available stock.

### AUT-07 — Implement atomic stock allocation (90 min)

Completion checklist:

- [ ] Lock or reserve selected PreOrders and stock in one transaction.
- [ ] Prevent concurrent schedulers and payment confirmations from allocating the same capacity.
- [ ] Add concurrent-allocation integration tests.

### AUT-08 — Implement marketplace creation dispatch (90 min)

Completion checklist:

- [ ] Convert committed execution intents into one external create operation per Client Order.
- [ ] Persist successful results and ambiguous outcomes for reconciliation.
- [ ] Add retry, crash, and duplicate-dispatch tests.

### AUT-09 — Implement Marketplace Order synchronization (90 min)

Completion checklist:

- [ ] Poll active attempts at the configurable synchronization interval.
- [ ] Validate status and quantities before applying an application use case.
- [ ] Add interval-change, unknown-status, and API-recovery tests.

### AUT-10 — Implement partial-fill tracking (75 min)

Completion checklist:

- [ ] Persist purchased and remaining quantities monotonically according to the approved contract.
- [ ] Reject quantity regressions, overfills, and mismatched totals.
- [ ] Add repeated and out-of-order synchronization tests.

### AUT-11 — Connect completion detection to finalization (60 min)

Completion checklist:

- [ ] Invoke the idempotent completion use case only after validated RBXCreate confirmation.
- [ ] Stop synchronization and reorder eligibility after completion.
- [ ] Add duplicate-completion and late-response tests.

### AUT-12 — Implement the shared reorder use case (90 min)

Completion checklist:

- [ ] Synchronize, cancel, confirm, calculate remaining quantity, and create a replacement through one workflow.
- [ ] Preserve the Client Order and all Marketplace Order history.
- [ ] Add completion-during-cancel, failed-cancel, partial-fill, and repeated-request tests.

### AUT-13 — Implement automatic reorder scheduling (75 min)

Completion checklist:

- [ ] Evaluate only Purchasing orders when automation is enabled and their interval is due.
- [ ] Apply runtime interval changes according to the approved policy.
- [ ] Add disabled, due, not-due, restart, and completion-stop tests.

### AUT-14 — Connect Manual Reorder to the shared workflow (45 min)

Completion checklist:

- [ ] Trigger the exact shared reorder use case from the authorized Telegram action.
- [ ] Record manual trigger metadata, timeline, and notification behavior.
- [ ] Test rapid repeated button presses and invalid order states.

### AUT-15 — Implement startup recovery inventory (75 min)

Completion checklist:

- [ ] Load unfinished Purchasing orders, PreOrders, pending notifications, and incomplete external operations.
- [ ] Leave Completed and Cancelled orders unchanged.
- [ ] Add restart-inventory tests with mixed states.

### AUT-16 — Implement incomplete-operation recovery (90 min)

Completion checklist:

- [ ] Reconcile create, cancellation, reorder, synchronization, and completion crash windows.
- [ ] Resume each operation idempotently without creating duplicate marketplace activity.
- [ ] Add a test for every persisted intermediate operation state.

### AUT-17 — Implement persistent notification delivery (90 min)

Completion checklist:

- [ ] Deliver stored notifications asynchronously with bounded retries and category settings.
- [ ] Track delivered, retryable, and permanently failed states without losing history.
- [ ] Add restart, duplicate-dispatch, Telegram-outage, and disabled-category tests.

### AUT-18 — Implement singleton job ownership (75 min)

Completion checklist:

- [ ] Use the approved lease or lock mechanism for each singleton background workflow.
- [ ] Support lease expiry and safe takeover after process failure.
- [ ] Prove two application instances cannot perform the same due operation concurrently.

### AUT-19 — Implement automation notifications and logging (60 min)

Completion checklist:

- [ ] Record required reorder, recovery, synchronization-failure, cancellation, and marketplace-error events.
- [ ] Apply notification category and global enablement settings.
- [ ] Verify technical logs and business timeline events remain distinct.

### AUT-20 — Phase 6 exit gate (60 min)

Completion checklist:

- [ ] Run automation, concurrency, fake-marketplace, and recovery suites.
- [ ] Demonstrate stock appearance through completed purchase using only Telegram and fake external services.
- [ ] Confirm no tested race or restart creates duplicate Marketplace Orders or purchases.

## Milestone 7 — Reporting

Corresponds to Phase 7 in `IMPLEMENTATION_PLAN.md`.

### RPT-01 — Define statistics calculations and period boundaries (60 min)

Completion checklist:

- [ ] Define each documented count, total, and average from authoritative entities.
- [ ] Define daily, weekly, and monthly boundaries using stored UTC and configured display timezone.
- [ ] Add calculation examples as tests.

### RPT-02 — Implement completed-order statistics projection (90 min)

Completion checklist:

- [ ] Update statistics idempotently from Completed orders only.
- [ ] Exclude Draft, PreOrder, Purchasing, and Cancelled financial activity.
- [ ] Add duplicate-event and rebuild-equivalence tests.

### RPT-03 — Implement daily, weekly, and monthly queries (75 min)

Completion checklist:

- [ ] Return approved order and financial metrics for each period.
- [ ] Handle timezone boundaries and empty periods correctly.
- [ ] Add month-end, week-boundary, and daylight-offset tests where applicable.

### RPT-04 — Implement Customer statistics and order history (60 min)

Completion checklist:

- [ ] Return Customer order counts, completed Robux, and chronological order history required by the UI.
- [ ] Include archived Customers without losing history.
- [ ] Add no-order, mixed-status, and archived-customer tests.

### RPT-05 — Implement financial summaries (75 min)

Completion checklist:

- [ ] Report purchased Robux, spending, commission, average rate, and average cost from finalized values.
- [ ] Avoid recalculating historical values with current settings.
- [ ] Add multi-rate and rounding tests.

### RPT-06 — Wire Telegram statistics and history views (75 min)

Completion checklist:

- [ ] Connect statistics, Customer history, order timeline, and financial summary screens to reporting queries.
- [ ] Format amounts, currencies, dates, and pagination consistently.
- [ ] Add Telegram reporting integration tests.

### RPT-07 — Implement System Status reporting (60 min)

Completion checklist:

- [ ] Report database, Telegram, RBXCreate, stock freshness, synchronization, and automation health safely.
- [ ] Expose actionable operator information without secrets or raw credentials.
- [ ] Add healthy, degraded, and unavailable-state tests.

### RPT-08 — Implement report consistency verification (60 min)

Completion checklist:

- [ ] Add a rebuild command or service that recomputes projections from immutable source data.
- [ ] Detect and report projection mismatches without changing completed business records.
- [ ] Test detection and safe repair of statistics-only drift.

### RPT-09 — Phase 7 exit gate (45 min)

Completion checklist:

- [ ] Run statistics, finance, history, and Telegram reporting suites.
- [ ] Rebuild statistics and compare them with incremental projections.
- [ ] Confirm all documented V1 metrics are available and no extra reporting scope was introduced.

## Milestone 8 — System hardening

Corresponds to Phase 8 in `IMPLEMENTATION_PLAN.md`.

### HRD-01 — Harden startup configuration validation (60 min)

Completion checklist:

- [ ] Validate credentials, intervals, rates, timezone, database connectivity, and incompatible settings before starting automation.
- [ ] Separate fatal startup failures from degraded external availability.
- [ ] Add invalid-production-configuration tests.

### HRD-02 — Harden Telegram authorization and input limits (60 min)

Completion checklist:

- [ ] Reject unauthorized users, oversized inputs, invalid callbacks, and replayed actions.
- [ ] Ensure every mutating use case verifies operator context.
- [ ] Add adversarial update tests.

### HRD-03 — Audit secret and log redaction (60 min)

Completion checklist:

- [ ] Exercise configuration, HTTP, exceptions, startup, and Telegram error paths with marker secrets.
- [ ] Verify marker secrets never appear in captured logs or messages.
- [ ] Document the safe fields allowed in marketplace communication logs.

### HRD-04 — Harden transaction and concurrency behavior (90 min)

Completion checklist:

- [ ] Review payment, scheduling, cancellation, reorder, completion, settings, and recovery transaction boundaries.
- [ ] Add missing locks, versions, constraints, or retry-on-conflict handling.
- [ ] Run concurrent mutation tests repeatedly without invariant failures.

### HRD-05 — Harden external-service resilience (75 min)

Completion checklist:

- [ ] Validate retry budgets, request throttling, connection limits, and permanent-failure notifications.
- [ ] Prevent tight retry loops after restart or sustained outages.
- [ ] Add prolonged-outage and recovery tests using fake servers.

### HRD-06 — Harden graceful startup and shutdown (75 min)

Completion checklist:

- [ ] Start components in the documented order and stop accepting new work before draining active operations.
- [ ] Close Telegram, HTTP, worker, and database resources cleanly.
- [ ] Add shutdown-during-work tests.

### HRD-07 — Add health and readiness checks (60 min)

Completion checklist:

- [ ] Expose internal liveness and readiness through the approved mechanism without creating a public business API.
- [ ] Distinguish database failure, external degradation, and recovery-in-progress states.
- [ ] Add health-state transition tests.

### HRD-08 — Review and tune database indexes (75 min)

Completion checklist:

- [ ] Inspect query plans for status lists, scheduler candidates, active attempts, timelines, notifications, and statistics.
- [ ] Add only indexes supported by observed query patterns.
- [ ] Record before-and-after query-plan evidence.

### HRD-09 — Add operational metrics and correlation context (75 min)

Completion checklist:

- [ ] Track job runs, API outcomes, synchronization lag, stock freshness, notification failures, and recovery outcomes.
- [ ] Correlate logs by Client Order and Marketplace Order without exposing secrets.
- [ ] Verify metric or log failure does not fail business operations.

### HRD-10 — Implement and verify database backup/restore (90 min)

Completion checklist:

- [ ] Define a repeatable PostgreSQL backup and restore procedure for all persistent business data.
- [ ] Restore into a clean environment and verify counts, histories, settings, and unfinished operations.
- [ ] Record the tested recovery result and limitations.

### HRD-11 — Harden container runtime configuration (75 min)

Completion checklist:

- [ ] Run containers as non-root with explicit volumes, restart policies, health checks, and bounded resources.
- [ ] Keep credentials outside images and source-controlled configuration.
- [ ] Verify restart and update preserve all persistent data.

### HRD-12 — Phase 8 exit gate (60 min)

Completion checklist:

- [ ] Run security, resilience, concurrency, backup/restore, and container checks.
- [ ] Confirm no critical warning, secret leak, or data-integrity defect remains.
- [ ] Record production-readiness gaps for Milestone 9 validation.

## Milestone 9 — Complete testing and validation

Corresponds to Phase 9 in `IMPLEMENTATION_PLAN.md`.

### TST-01 — Build the requirement traceability matrix (90 min)

Completion checklist:

- [ ] Map every `REQ`, `BR`, `DB`, `ARC`, `UI`, `API`, `ALG`, `DEP`, and `TEST` identifier to implementation and tests.
- [ ] Mark unresolved, partially covered, and not-applicable entries with justification.
- [ ] Confirm every Business Rule has explicit test coverage.

### TST-02 — Audit and close unit-test gaps (90 min)

Completion checklist:

- [ ] Review Customer, ClientOrder, MarketplaceOrder, Finance, Statistics, Scheduler, Automation, Settings, and Recovery units.
- [ ] Add missing success, boundary, failure, and idempotency cases that fit this task.
- [ ] Split any remaining gap set into additional 30–90 minute tasks.

### TST-03 — Complete database integration coverage (90 min)

Completion checklist:

- [ ] Cover migrations, constraints, repositories, transaction rollback, locks, immutability, and restart persistence.
- [ ] Run against the supported PostgreSQL 17 configuration.
- [ ] Verify tests leave no state dependency between cases.

### TST-04 — Complete Telegram integration coverage (90 min)

Completion checklist:

- [ ] Cover authorization, navigation, all screens, all actions, pagination, invalid input, and callback replay.
- [ ] Verify the full operator workflow requires no RBXCreate website interaction.
- [ ] Confirm handlers remain responsive during application operations.

### TST-05 — Complete external API contract coverage (75 min)

Completion checklist:

- [ ] Cover every approved RBXCreate and Roblox endpoint, status, error, timeout, and rate-limit response.
- [ ] Verify unexpected responses cannot mutate business state.
- [ ] Confirm the suite is isolated from production services.

### TST-06 — Add the end-to-end happy-path suite (90 min)

Completion checklist:

- [ ] Cover new and existing Customers, auto/manual Place ID, direct purchase, PreOrder scheduling, reorder, completion, reporting, and notifications.
- [ ] Assert final database entities and timeline order.
- [ ] Run the suite entirely with disposable infrastructure and fake external APIs.

### TST-07 — Add marketplace and network failure scenarios (90 min)

Completion checklist:

- [ ] Cover RBXCreate unavailable, authentication failure, timeout, malformed response, rate limiting, and network interruption.
- [ ] Verify bounded retry, notification, and eventual recovery behavior.
- [ ] Assert business entities remain consistent throughout.

### TST-08 — Add database and Telegram failure scenarios (75 min)

Completion checklist:

- [ ] Cover database unavailability, transaction interruption, Telegram outage, and notification-delivery failure.
- [ ] Verify business commits do not depend on notification delivery or SystemLog persistence.
- [ ] Verify pending work resumes after the dependency recovers.

### TST-09 — Add create and cancellation recovery tests (90 min)

Completion checklist:

- [ ] Restart before request, after request, after remote success, before local commit, and after local commit.
- [ ] Exercise both Marketplace Order creation and cancellation windows.
- [ ] Assert reconciliation produces no duplicate active order or purchase.

### TST-10 — Add reorder and completion recovery tests (90 min)

Completion checklist:

- [ ] Restart during synchronization, partial fill, automatic reorder, manual reorder, and completion finalization.
- [ ] Verify recovery preserves the Client Order and historical Marketplace Orders.
- [ ] Assert financial and statistics effects occur exactly once.

### TST-11 — Add concurrency and duplicate-prevention tests (90 min)

Completion checklist:

- [ ] Race payment confirmations, scheduler runs, manual reorder clicks, synchronization, cancellation, and recovery ownership.
- [ ] Verify database and service-level safeguards agree.
- [ ] Run repeated stress iterations with zero duplicate active orders or completions.

### TST-12 — Add scheduler performance tests (75 min)

Completion checklist:

- [ ] Measure deterministic scheduling for documented “dozens of simultaneous orders” scenarios.
- [ ] Include worst-case approved quantities and tie patterns.
- [ ] Confirm execution stays within the approved monitoring-response budget.

### TST-13 — Run restart and long-operation validation (90 min)

Completion checklist:

- [ ] Exercise repeated controlled restarts with mixed Draft, PreOrder, Purchasing, Completed, and Cancelled data.
- [ ] Verify monitoring, synchronization, reorder, notifications, and leases resume correctly.
- [ ] Compare business and statistics consistency before and after the run.

### TST-14 — Run final business acceptance validation (90 min)

Completion checklist:

- [ ] Execute every acceptance criterion from `PROJECT_REQUIREMENTS.md`, `BUSINESS_RULES.md`, and the domain documents.
- [ ] Record evidence for pass, failure, or explicitly approved exception.
- [ ] Confirm no critical defect remains.

### TST-15 — Phase 9 exit gate (45 min)

Completion checklist:

- [ ] Run the complete lint, unit, integration, contract, business, recovery, concurrency, and performance suites.
- [ ] Confirm the traceability matrix has no unexplained gaps.
- [ ] Approve or reject progression to production release preparation.

## Milestone 10 — Release

Corresponds to Phase 10 in `IMPLEMENTATION_PLAN.md`.

### REL-01 — Create production Docker Compose configuration (75 min)

Completion checklist:

- [ ] Configure production services, persistent volumes, health checks, restart policies, and approved network exposure.
- [ ] Keep environment-specific values and secrets external.
- [ ] Validate the rendered configuration without exposing credentials.

### REL-02 — Automate migration and startup ordering (75 min)

Completion checklist:

- [ ] Ensure migrations complete successfully before bot or automation work starts.
- [ ] Fail safely on migration or database compatibility errors.
- [ ] Test clean install and upgrade from the previous migration state.

### REL-03 — Prepare production configuration guidance (60 min)

Completion checklist:

- [ ] Document every required variable, valid range, secret source, and safe rotation procedure.
- [ ] Include timezone, notification, monitoring, synchronization, reorder, finance, and marketplace settings.
- [ ] Verify examples contain no real credentials.

### REL-04 — Prepare deployment, update, and rollback runbooks (75 min)

Completion checklist:

- [ ] Document clean deployment, health verification, backup, update, rollback, and recovery steps.
- [ ] Include expected behavior for unfinished business operations.
- [ ] Dry-run the commands in a disposable environment.

### REL-05 — Deploy and validate a staging environment (90 min)

Completion checklist:

- [ ] Deploy from the production artifacts with non-production credentials and persistent data.
- [ ] Run startup, Telegram, database, fake/sandbox marketplace, and health smoke tests.
- [ ] Record version, configuration checksum, and validation outcome without secrets.

### REL-06 — Perform staging restart and update rehearsal (90 min)

Completion checklist:

- [ ] Restart during waiting and purchasing scenarios and verify automatic recovery.
- [ ] Apply an application update without recreating the database or losing history.
- [ ] Verify rollback restores service without duplicating external operations.

### REL-07 — Complete the release security and data review (60 min)

Completion checklist:

- [ ] Verify operator authorization, secret storage, log redaction, backup access, and network exposure.
- [ ] Verify Completed orders, financial history, timeline, and Marketplace Order history remain immutable.
- [ ] Confirm no production credential exists in repository history or images.

### REL-08 — Complete the Version 1 release checklist (60 min)

Completion checklist:

- [ ] Confirm every prior milestone exit gate and final acceptance criterion is complete.
- [ ] Record approved known limitations without adding future-version functionality.
- [ ] Approve the production release candidate as Version 1.0.

### REL-09 — Perform production deployment validation (90 min)

Completion checklist:

- [ ] Deploy the approved release and verify migrations, health, Telegram authorization, and external connectivity.
- [ ] Confirm recovery, monitoring, synchronization, and notification workers are active exactly once.
- [ ] Record deployment evidence without exposing sensitive information.

### REL-10 — Close the Version 1 release (45 min)

Completion checklist:

- [ ] Confirm the operator can complete the documented workflow entirely through Telegram.
- [ ] Confirm backup, restore, update, rollback, monitoring, and incident procedures are available.
- [ ] Mark Version 1 complete only after all mandatory requirements and tests pass.

## Definition of done for every implementation task

In addition to its task-specific checklist, each implementation task is complete only when:

- [ ] The change follows the documented architecture and Business Rules.
- [ ] Relevant tests pass and no existing test regresses.
- [ ] Ruff and static validation pass without new warnings.
- [ ] Secrets and sensitive values are absent from code, logs, fixtures, and output.
- [ ] The change is small enough for an independent review and contains no unrelated work.
