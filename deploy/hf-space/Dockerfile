# The Hugging Face Space's image.
#
# One line on purpose. The Space does not build Helix — it runs the image that
# CI already built, tested and published, so what serves traffic here is bit
# for bit what `docker pull` gives anyone else. Building from source in the
# Space would fork that: a second build, on different hardware, of a tree
# nobody tagged.
#
# Everything the runtime needs is already baked in and is inherited from this
# line: USER helix (non-root), EXPOSE 8000, the MiniLM weights, and the CMD
# that starts uvicorn with one worker. There is deliberately nothing else in
# this file — every addition would be a way for the Space to differ from the
# artifact it is supposed to be running.
#
# To move to a newer release, change the tag and push. Pin an exact version,
# never `latest`: a Space that changes version on its next rebuild is one
# nobody can debug afterwards, because "what was running?" has no answer.
FROM ghcr.io/achindra2003/helix:v0.9.0-rc1
