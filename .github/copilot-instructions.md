## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your first action should be `graphify query "<question>"` when `graphify-out/graph.json`
exists. Use `graphify path "<A>" "<B>"` for relationship questions and `graphify explain "<concept>"`
for focused-concept questions. These return a scoped subgraph, usually much smaller than the full
report or raw grep output.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.

## Appcreations project memory

At the start of a session, read `E:\Appcreations\_KnowledgeBase\Projects\youtube-saved-video-organizer.md`
and any relevant recent handoff notes in `E:\Appcreations\_KnowledgeBase\Logs`.
Use the vault as orientation, not as a substitute for checking the current code,
README, Git state, and tests. When asked to save a handoff, write a concise note
using the vault's `Templates/Session Log.md`. Never copy secrets, credentials,
tokens, private user data, or full chat transcripts into the vault.

This repository contains OAuth credentials and local configuration. Exclude them
from Graphify inputs and keep all generated Graphify outputs local.
