# Distributed Infrastructure Control Plane --- Full Demo Guide

## Project

**Distributed Infrastructure Control Plane with Eventual Consistency and
State Reconciliation**

This guide maps every required work item to a live or test-based
demonstration.

------------------------------------------------------------------------

## 0. Start the Project

``` bash
cd ~/XQORA/Project/PR\ 1/distributed-control-plane
docker compose up -d
docker compose ps
```

Expected services:

-   control-plane-api
-   control-plane-controller
-   control-plane-event-consumer
-   control-plane-postgres
-   control-plane-redis

Open Swagger:

``` text
http://localhost:8000/docs
```

Before starting, explain:

> The user declares a desired infrastructure state. The control plane
> stores it, publishes an event, observes the real infrastructure,
> compares desired and observed state, detects drift, and reconciles
> until the states converge.

Core flow:

``` text
User
 ↓
Swagger / FastAPI
 ↓
Desired State → PostgreSQL
 ↓
Redis Stream Event
 ↓
Event Consumer
 ↓
Controller
 ↓
Reconciler
 ↓
Docker Infrastructure
 ↓
Observed State
 ↓
Compare Desired vs Observed
 ├─ Match → READY
 └─ Different → DRIFTED → RECONCILE → READY
```

------------------------------------------------------------------------

# 1. Distributed Control-Plane Architecture

### Requirement

**Design a distributed control-plane architecture.**

### Demo

Show:

``` bash
docker compose ps
```

Then show Swagger:

``` text
http://localhost:8000/docs
```

Explain the components:

``` text
FastAPI
 ├── PostgreSQL
 └── Redis Streams
       ↓
Event Consumer
       ↓
Controller
       ↓
Reconciler
       ↓
Docker Infrastructure
```

### Say

> This is our distributed control-plane architecture. The API handles
> requests, PostgreSQL stores state, Redis Streams provides asynchronous
> events, the controller processes those events, and the reconciler
> manages the infrastructure.

------------------------------------------------------------------------

# 2. Desired State and Observed State

### Requirement

**Define desired state and observed state models.**

### Demo

In Swagger open:

`POST /resources`

Click **Try it out** and use:

``` json
{
  "name": "presentation-demo",
  "resource_type": "container",
  "desired_state": {
    "image": "nginx:alpine",
    "replicas": 2
  }
}
```

If the API exposes `Idempotency-Key`, use:

``` text
presentation-demo-001
```

Click **Execute**.

Then use:

`GET /resources`

This endpoint has **no parameters**. Click **Try it out → Execute**.

Find `presentation-demo`.

Expected eventually:

``` text
desired_state:
  image: nginx:alpine
  replicas: 2

observed_state:
  running_replicas: 2

status:
  READY
```

### Say

> Desired state describes what the user wants. Observed state describes
> what actually exists in Docker. When both match, the resource becomes
> READY.

------------------------------------------------------------------------

# 3. Resource Registration and Lifecycle

### Requirement

**Implement resource registration and lifecycle management.**

Use these Swagger endpoints:

``` text
POST   /resources
GET    /resources
GET    /resources/{resource_id}
PUT    /resources/{resource_id}
DELETE /resources/{resource_id}
POST   /resources/{resource_id}/sync
```

### Update demo

Use:

`PUT /resources/{resource_id}`

Example:

``` json
{
  "desired_state": {
    "image": "nginx:alpine",
    "replicas": 3
  },
  "expected_version": 1
}
```

Then verify with:

`GET /resources/{resource_id}`

Expected:

``` text
desired replicas = 3
observed replicas = 3
status = READY
```

### Lifecycle

``` text
Create
 ↓
PENDING
 ↓
RECONCILING
 ↓
READY
 ↓
Update / Drift
 ↓
RECONCILING
 ↓
READY
 ↓
Delete
 ↓
DELETING
 ↓
DELETED
```

### Say

> The API supports registration, inspection, updates, synchronization,
> and deletion, giving the resource a complete lifecycle.

------------------------------------------------------------------------

# 4. Event-Driven State Updates

### Requirement

**Build event-driven state updates.**

Open another terminal:

``` bash
docker compose logs -f event-consumer
```

Then create or update a resource from Swagger.

Look for messages such as:

``` text
Processing event ... ResourceCreated
```

or:

``` text
Processing event ... ResourceUpdated
```

### Flow

``` text
API
 ↓
Database
 ↓
Redis Stream
 ↓
Event Consumer
 ↓
Reconciliation
```

### Say

> Resource changes are propagated through Redis Streams. The event
> consumer receives the event and triggers reconciliation instead of
> requiring all components to be tightly coupled.

------------------------------------------------------------------------

# 5. Eventual Consistency

### Requirement

**Handle eventual consistency between distributed components.**

Immediately after creating a resource, it may be:

``` text
PENDING
```

Then, after the event is processed:

``` text
READY
```

Explain:

``` text
T1:
Desired = 2
Observed = empty
Status = PENDING

T2:
Event processed

T3:
Docker containers created

T4:
Observed = 2
Status = READY
```

### Say

> The components do not have to become consistent at exactly the same
> instant. They temporarily converge through event processing and
> reconciliation. Eventually the desired and observed states become
> consistent.

------------------------------------------------------------------------

# 6. Reconciliation Loops

### Requirement

**Implement reconciliation loops.**

The reconciliation logic is:

``` text
Observe
 ↓
Compare
 ├─ Same → READY
 └─ Different
       ↓
   Reconcile
       ↓
   Observe again
       ↓
     READY
```

Use:

`GET /resources/{resource_id}`

to show:

-   desired state
-   observed state
-   status

### Say

> The reconciler does not assume the infrastructure is correct. It
> observes the actual state, compares it with desired state, performs
> corrective actions, and observes again.

------------------------------------------------------------------------

# 7. Infrastructure Drift Detection and Recovery

### Requirement

**Detect configuration and infrastructure drift.**

This is the most important live demo.

### Step 1 --- Confirm healthy state

Swagger:

`GET /resources/{resource_id}`

Show:

``` text
desired replicas = 2
observed replicas = 2
status = READY
```

### Step 2 --- Show actual Docker containers

``` bash
docker ps --filter "label=control-plane-resource=presentation-demo"
```

### Step 3 --- Create drift

Get the container names:

``` bash
docker ps --filter "label=control-plane-resource=presentation-demo" --format "{{.Names}}"
```

Stop one returned container:

``` bash
docker stop presentation-demo-1
```

If the actual name differs, use the name returned by the previous
command.

Now:

``` text
Desired = 2
Observed = 1
```

### Step 4 --- Check through Swagger

Use:

`GET /resources/{resource_id}`

The status may move through:

``` text
DRIFTED
RECONCILING
READY
```

depending on controller timing.

### Step 5 --- Manual sync

Use:

`POST /resources/{resource_id}/sync`

Click:

**Try it out → Execute**

### Step 6 --- Verify

Use:

`GET /resources/{resource_id}`

Expected:

``` text
desired replicas = 2
observed replicas = 2
status = READY
```

Then:

``` bash
docker ps --filter "label=control-plane-resource=presentation-demo"
```

### Say

> I intentionally changed the infrastructure outside the control plane.
> The desired state still requires two replicas, but only one is
> running. This is drift. The reconciliation process detects the
> difference and brings the infrastructure back to the desired state.

------------------------------------------------------------------------

# 8. Partial Failures, Retries, and Stale State

### Requirement

**Recover from partial failures and stale state.**

Implemented fields:

``` text
retry_count
max_retries
next_retry_at
last_error
```

Retry flow:

``` text
Failure
 ↓
retry_count++
 ↓
Exponential backoff
 ↓
Retry
 ├─ Success → READY
 └─ Failure → retry again
```

Backoff:

``` text
Retry 1 → 2 seconds
Retry 2 → 4 seconds
Retry 3 → 8 seconds
...
```

Maximum failures lead to:

``` text
FAILED
```

### Safe presentation demo

Run:

``` bash
docker compose exec api pytest -q tests/test_retry_behavior.py
```

Expected:

``` text
4 passed
```

### Say

> We tested infrastructure failures using a mocked infrastructure
> adapter. The system records the error, increments the retry count,
> schedules retries with exponential backoff, and eventually enters
> FAILED after the retry limit. Successful recovery clears the retry
> state.

### Stale state

Explain:

> API updates use resource versions, so a stale client cannot overwrite
> a newer version. The reconciler also re-observes infrastructure
> instead of permanently trusting an old observation.

------------------------------------------------------------------------

# 9. Resource Dependencies and Ordering

### Requirement

**Maintain resource dependencies and ordering.**

Example:

``` text
database
   ↓
backend
   ↓
frontend
```

A resource can contain:

``` json
{
  "dependencies": ["database"]
}
```

The controller uses dependency checks and topological ordering.

### Say

> A dependent resource should not be reconciled before its required
> dependency is ready. We implemented dependency checks and topological
> ordering using Kahn's algorithm.

If a dependency is missing or not READY:

``` text
BLOCKED
```

------------------------------------------------------------------------

# 10. Idempotent Operations

### Requirement

**Implement idempotent operations.**

Use:

`POST /resources`

First request:

``` text
Idempotency-Key:
presentation-idempotency-001
```

Body:

``` json
{
  "name": "idempotency-demo",
  "resource_type": "container",
  "desired_state": {
    "image": "nginx:alpine",
    "replicas": 1
  }
}
```

Send the exact same request again with the same key.

The system should not create a duplicate.

### Conflict test

Reuse the same key but change the request.

Expected:

``` text
409 Conflict
```

### Say

> Idempotency makes client retries safe. The same request with the same
> idempotency key does not create a duplicate. Reusing the key for a
> different request is rejected.

------------------------------------------------------------------------

# 11. Infrastructure State Transitions

### Requirement

**Track infrastructure state transitions.**

Implemented states:

``` text
PENDING
RECONCILING
READY
DRIFTED
BLOCKED
FAILED
DELETING
DELETED
```

Example:

``` text
PENDING
 ↓
RECONCILING
 ↓
READY
 ↓
DRIFTED
 ↓
RECONCILING
 ↓
READY
```

The reconciliation service validates allowed transitions.

### Demo

Use:

`GET /resources/{resource_id}/history`

after the drift demo.

### Say

> We implemented a formal state machine so resources cannot move
> arbitrarily between states. Valid transitions are explicitly defined
> and validated.

------------------------------------------------------------------------

# 12. Resource Management and Orchestration APIs

### Requirement

**Provide APIs for resource management and orchestration.**

Show Swagger:

``` text
POST   /resources
GET    /resources
GET    /resources/{id}
GET    /resources/{id}/history
PUT    /resources/{id}
DELETE /resources/{id}
POST   /resources/{id}/sync
```

Explain:

> These APIs provide the external control interface for resource
> registration, inspection, updates, deletion, synchronization, and
> audit history.

No need to execute every endpoint here because they are demonstrated
elsewhere.

------------------------------------------------------------------------

# 13. State History and Audit Information

### Requirement

**Create state history and audit information.**

Use:

`GET /resources/{resource_id}/history`

Click **Try it out**, enter the resource ID, then **Execute**.

History contains information such as:

``` text
event_type
status
version
desired_state
observed_state
message
created_at
```

A lifecycle can look like:

``` text
ResourceCreated
 ↓
STATE_OBSERVED
 ↓
DRIFT_DETECTED
 ↓
RECONCILIATION
 ↓
READY
```

### Say

> The history provides an audit trail showing what happened to the
> resource and how its state changed over time.

------------------------------------------------------------------------

# 14. Concurrent Updates and Conflicting State Changes

### Requirement

**Test concurrent updates and conflicting state changes.**

The project uses:

``` text
version
expected_version
```

Example:

``` text
Current version = 1
```

Client A:

``` json
{
  "desired_state": {
    "image": "nginx:alpine",
    "replicas": 2
  },
  "expected_version": 1
}
```

This succeeds and produces:

``` text
version = 2
```

Client B still sends:

``` json
{
  "desired_state": {
    "image": "nginx:alpine",
    "replicas": 3
  },
  "expected_version": 1
}
```

Expected:

``` text
409 Conflict
```

### Automated demo

``` bash
docker compose exec api pytest -q tests/test_api_behavior.py
```

The suite includes:

``` text
test_concurrent_updates_conflict
```

### Say

> Optimistic concurrency control prevents a stale client from
> overwriting a newer state. The API compares the expected version with
> the current version and returns 409 when they differ.

------------------------------------------------------------------------

# 15. Final End-to-End Demo

If the coordinator gives limited time, prioritize this scenario.

## Step 1 --- Create

Swagger:

`POST /resources`

Create:

``` text
presentation-demo
nginx:alpine
2 replicas
```

Say:

> I am declaring the desired state.

## Step 2 --- Observe

Swagger:

`GET /resources`

Show:

``` text
PENDING → READY
```

## Step 3 --- Verify Docker

``` bash
docker ps --filter "label=control-plane-resource=presentation-demo"
```

Show two containers.

## Step 4 --- Create drift

``` bash
docker stop presentation-demo-1
```

Use the actual container name if different.

## Step 5 --- Show drift

Swagger:

`GET /resources/{resource_id}`

Explain:

``` text
Desired = 2
Observed = 1
```

## Step 6 --- Reconcile

Swagger:

`POST /resources/{resource_id}/sync`

## Step 7 --- Verify recovery

Swagger:

`GET /resources/{resource_id}`

Show:

``` text
Desired = 2
Observed = 2
Status = READY
```

## Step 8 --- Show history

Swagger:

`GET /resources/{resource_id}/history`

Show the recorded lifecycle.

Say:

> This single workflow demonstrates desired state, observed state,
> eventual consistency, reconciliation, drift detection, recovery, state
> transitions, and audit history.

------------------------------------------------------------------------

# 16. Final Test

Run:

``` bash
docker compose exec api pytest -q
```

Current expected result:

``` text
48 passed
```

Say:

> We have automated tests covering state transitions, API behavior,
> reconciliation, retries, dependencies, idempotency, and concurrent
> update conflicts.

------------------------------------------------------------------------

# 17. Requirement-to-Demo Checklist

  -----------------------------------------------------------------------
  Requirement                         Demonstration
  ----------------------------------- -----------------------------------
  Distributed control-plane           Docker Compose + component
  architecture                        explanation

  Desired/observed state              POST resource + GET resource

  Resource registration/lifecycle     POST, GET, PUT, DELETE

  Event-driven updates                Redis/event-consumer logs

  Eventual consistency                PENDING → READY

  Reconciliation loops                Desired vs observed comparison

  Drift detection                     Stop a container

  Partial failure recovery            Retry tests

  Stale state                         Resource version / 409

  Dependencies/order                  database → backend → frontend

  Idempotency                         Same Idempotency-Key twice

  State transitions                   State machine + history

  APIs/orchestration                  Swagger endpoints

  History/audit                       GET `/resources/{id}/history`

  Concurrent updates                  Version conflict / 409
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# 18. One-Sentence Answers for Rapid Questions

**Architecture:**\
\> We separated the API, state store, event system, controller,
reconciler, and infrastructure adapter.

**Desired vs observed:**\
\> Desired state is what the user wants; observed state is what actually
exists.

**Lifecycle:**\
\> Resources can be created, updated, reconciled, and deleted through
the API.

**Events:**\
\> Redis Streams carries resource lifecycle events to the event
consumer.

**Eventual consistency:**\
\> Components can temporarily have different states, but reconciliation
eventually brings them into convergence.

**Reconciliation:**\
\> The reconciler compares desired and observed state and applies
corrective actions.

**Drift:**\
\> We detect differences in replica count and image configuration and
reconcile them.

**Failure recovery:**\
\> Failed infrastructure operations use retries with exponential backoff
and a maximum retry limit.

**Dependencies:**\
\> Resources are reconciled according to dependency order using
topological sorting.

**Idempotency:**\
\> The same request with the same idempotency key does not create
duplicate resources.

**State transitions:**\
\> We validate transitions between PENDING, RECONCILING, READY, DRIFTED,
BLOCKED, FAILED, DELETING, and DELETED.

**APIs:**\
\> FastAPI provides REST endpoints for resource management and
orchestration.

**Audit:**\
\> State history records resource events, versions, states, and
timestamps.

**Concurrency:**\
\> Optimistic concurrency control rejects updates that use an outdated
resource version.

------------------------------------------------------------------------

# 19. Final Presentation Script

> "The main purpose of this project is to automate infrastructure state
> management using the control-plane pattern. The user declares the
> desired state, the system stores and propagates that state through
> distributed components, observes the actual infrastructure, detects
> drift, and reconciles the infrastructure until the desired and
> observed states converge.
>
> In addition, we implemented dependency ordering, idempotent
> operations, optimistic concurrency control, retry and failure
> recovery, formal state transitions, REST APIs, and state history.
>
> The key demonstration is that if the desired state requires two
> containers and one is manually stopped, the control plane detects the
> drift and reconciles the infrastructure back to two running
> containers."

------------------------------------------------------------------------

# 20. Final Checklist

``` text
[ ] docker compose up -d
[ ] docker compose ps
[ ] Swagger opens
[ ] Create demo resource
[ ] Know the resource ID
[ ] Show desired state
[ ] Show PENDING → READY
[ ] Show Docker containers
[ ] Stop one demo container
[ ] Show drift
[ ] Trigger /sync
[ ] Show recovery
[ ] Show history
[ ] Demonstrate update/scaling
[ ] Demonstrate idempotency
[ ] Explain dependencies
[ ] Demonstrate concurrency conflict
[ ] Run pytest
[ ] Confirm 48 tests pass
```

## Core workflow to memorize

``` text
CREATE
  ↓
PENDING
  ↓
READY
  ↓
STOP CONTAINER
  ↓
DRIFT
  ↓
SYNC
  ↓
RECONCILE
  ↓
READY
  ↓
HISTORY
```
