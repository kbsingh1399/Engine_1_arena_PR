# DeepSeek Harness Architecture & Coding Principles
Based on the DeepSeek Harness (Cordis) plugin architecture:

## 1. Plugin-First Foundation
- **Everything is a plugin**: Functionality is modular and mounted dynamically.
- **Registrations are effects**: Every contribution must go through `ctx.effect()` or `ctx.on()`, returning the disposer immediately.

## 2. Invariants & Types
- **Trust TypeScript at typed same-process boundaries**: Do not add redundant runtime validation for values the static interface already requires. Validate only at wire, file, queue, or process boundaries.
- **Switch on discriminant tags**: Closed unions must end in `assertNever` to guarantee completeness.
- **Opaque cross-boundary IDs**: Use branded types (e.g., `Branded<T>`) for cross-boundary IDs, never bare strings.

## 3. Events & Logging
- **Model-visible ⟺ Logged**: Anything reaching the model must be reconstructable from the session log.
- **Typed events via declaration merging**: Event structures should be extensible.
- **Waterfall listeners**: Listeners in a waterfall sequence MUST explicitly call `next()` to delegate; returning without it short-circuits the chain.

## 4. Development Principles
- **Foundation over blast radius**: In early development, prioritize architectural correctness over backwards-compatibility shims.
- **Tests describe behavior, not correctness**: Tests validate that behavior matches intent.
- **No hardcoded tunables**: Deployment-varying choices must be validated `Config` fields, not constants or test hooks.
- **Misconfiguration fails loud**: Fail at load time when self-contained; never silently skip a missing referent.
