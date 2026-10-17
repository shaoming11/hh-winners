"""Optional language layer: protocol text -> steps from the fixed vocabulary -> steps.validate -> operator approval.

The model only proposes; benchsim.process.steps.validate is the gate and an operator approves. See benchsim.ai.pipeline.
The Anthropic SDK is an optional extra (``uv pip install -e '.[ai]'``); without it the preset demo protocol is used."""
