# Local Engine Launch Recipes

AgentBlaster launch recipes render reviewable commands for starting local engines and registering matching provider profiles. Recipes do not execute commands, start processes, read secrets, or modify provider config unless the operator runs the rendered commands manually.

## Commands

List supported recipe templates:

```bash
agentblaster engines launch-recipes --catalog
```

Render a consolidated local-engine onboarding checklist:

```bash
agentblaster engines onboarding --format markdown --output reports/local-engine-onboarding.md
agentblaster engines onboarding --format json --output reports/local-engine-onboarding.json
agentblaster engines improvement-plan --engine afm --pressure-audit reports/qwen-gemma-stress-pressure.json --provider-contract-matrix reports/qwen-gemma-provider-contract-matrix.json --output-json reports/afm-improvement-plan.json
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

Render an LM Studio Anthropic-compatible recipe:

```bash
agentblaster engines launch-recipes \
  --engine lm-studio-anthropic \
  --model mlx-community/Qwen3.6-27B \
  --provider-name lm-studio-anthropic-qwen
```

## Safety

The output includes setup commands, launch commands, `agentblaster providers add` commands, non-secret protocol headers such as `anthropic-version`, and post-launch checks. The command renderer itself is static and side-effect free. Review the generated commands against the installed engine version before use.

## Target Catalog

Launch recipes answer how to start or register an engine profile. The engine target catalog answers what each engine should be compared against and which telemetry profile to expect:

```bash
agentblaster engines targets
agentblaster engines targets --target afm-mlx --format json
```

The onboarding artifact joins both sides. Each local engine entry includes the provider preset, reviewable launch recipe, matching engine target ID, primary scoring contract, telemetry profiles, workflow surfaces, representative agent profiles, prefill/concurrency challenge classes, native telemetry profiles, and native metric claim policy. This is static setup metadata; it does not launch engines, probe endpoints, resolve secrets, or write provider configuration.
