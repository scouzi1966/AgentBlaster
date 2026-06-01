# Local Engine Launch Recipes

AgentBlaster launch recipes render reviewable commands for starting local engines and registering matching provider profiles. Recipes do not execute commands, start processes, read secrets, or modify provider config unless the operator runs the rendered commands manually.

## Commands

List supported recipe templates:

```bash
agentblaster engines launch-recipes --catalog
```

Render an AFM recipe as Markdown:

```bash
agentblaster engines launch-recipes \
  --engine afm \
  --model mlx-community/Qwen3.6-27B \
  --markdown \
  --output-json reports/afm-launch-recipe.json
```

Render an Ollama native recipe:

```bash
agentblaster engines launch-recipes \
  --engine ollama-native \
  --model qwen3.6:27b \
  --provider-name ollama-qwen-native
```

## Safety

The output includes setup commands, launch commands, `agentblaster providers add` commands, and post-launch checks. The command renderer itself is static and side-effect free. Review the generated commands against the installed engine version before use.

## Target Catalog

Launch recipes answer how to start or register an engine profile. The engine target catalog answers what each engine should be compared against and which telemetry profile to expect:

```bash
agentblaster engines targets
agentblaster engines targets --target afm-mlx --format json
```
