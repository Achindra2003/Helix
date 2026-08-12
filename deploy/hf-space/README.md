---
title: Helix
emoji: 🧬
colorFrom: red
colorTo: yellow
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# Helix

**The AI workspace that remembers what your team already figured out.**

Shared, branchable AI conversations where the record compounds: start typing a
question and Helix resurfaces the teammate's thread that already explored it;
answers ground on your own documents with citations; every fork, run and source
stays visible to the whole room, live.

Source, tests and self-hosting instructions:
**https://github.com/Achindra2003/Helix**

---

`app_port: 8000` above is load-bearing. Spaces default to 7860 and the image
serves the API *and* the built frontend on 8000 — with the default, the Space
builds cleanly, starts cleanly, and then times out waiting for a port nothing
is listening on.
