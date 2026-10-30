# fixalong

A hands-free repair guide for Meta Quest 3. Tell it what's wrong, and an agent built on Meta's models looks through the headset's cameras, works out the cause, and guides you through the fix one checked step at a time.

Built for the Meta Global AI Developer Hackathon (Indie track, "Build for Your World"). Everything in this repo was built during the event.

## Layout

| Folder | What |
|---|---|
| `server/` | Python agent server: the agent loop, safety gates, and Meta Model API calls |
| `unity/` | Quest 3 client (Unity) |
| `docs/` | Plan and design notes |

See [docs/plan.md](docs/plan.md) for the plan.
