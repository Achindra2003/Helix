"""The conversation engine — Helix's core.

A single streamed-and-persisted "run" flows through here: a prompt goes in, an
event stream comes out (`user_node` -> `token`... -> `assistant_node` -> `done`),
and the turns are persisted as nodes on a branch. Two producers speak this same
event language — `ChatProducer` (a plain streamed completion) now, and
`DeepReasoningProducer` (Ouroboros) later — so the everyday chat and the
deep-reasoning power tool bolt onto the same mount.

The engine talks only to interfaces (`ConversationStore`, the producers), never
to the database or the UI directly, so it is built and tested on its own
(`InMemoryStore` + the stub provider). The DB-backed store and the frontend plug
into the seams afterward without touching engine code.
"""
