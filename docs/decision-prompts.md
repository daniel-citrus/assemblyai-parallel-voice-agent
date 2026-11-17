# Give your voice agent a decision to make

Start with the answer your caller needs. “What does Python 3.13 support?” needs an explanation backed by sources. “Which support label should I put in my compatibility table?” needs a value with a consistent meaning. Both can use the same evidence.

## Tell the voice agent when to call

The starter already exposes both tools. To build a compatibility assistant, add this to `INSTRUCTIONS` in [agent.py](../src/agent.py), restart, and try the two turns below.

> Help me fill in a library compatibility table. For factual lookups, use Search when you need outside evidence. When I give you support labels and ask you to classify a feature, use Decisions. Carry the project, version, and feature forward from the conversation. If a missing detail would change the label, ask one short question.

1. “What does Python 3.13 offer for free threading?” Search can find the release documentation and explain the feature.
2. “Classify that support as stable, experimental, or explicitly unsupported.” Decisions can fill in the table entry. The caller supplied the options. The agent can resolve “that support” from the first turn.

A plain yes/no question can still be a Search lookup. The hosted Decisions tool accepts an explicit request for Decisions, a probability, a choice among supplied options, or a score on a supplied scale. Calling it directly is enough once the subject and criteria are known. [Parallel MCP tool reference](https://docs.parallel.ai/integrations/mcp/quickstart#web_decisions)

## Tell Decisions what counts

The voice prompt controls routing. The arguments sent to Decisions define the judgment. For the second turn, the agent can send:

```json
{
  "state": {"project": "CPython", "version": "3.13", "feature": "free-threaded builds"},
  "questions": {
    "support_status": {
      "type": "choice",
      "instructions": "Classify free-threaded builds for this release using the official Python documentation. If the evidence cannot distinguish these labels, decline to decide.",
      "criteria": {
        "stable": "The project documents stable, non-experimental support.",
        "experimental": "The project documents support and marks it experimental.",
        "explicitly_unsupported": "The project explicitly states this feature is unsupported in this release."
      }
    }
  }
}
```

Read back the label and the evidence behind it in one sentence. If the tool declines or the source is about a different release, tell the caller you couldn't verify the label. Missing documentation alone doesn't establish that a feature is unsupported.

For a probability, use `noul` and define one claim that could be true or false. For a score, define what each level means and order the levels from lowest to highest. A request like “Should we upgrade?” needs the caller's criterion first. Asking “Which package do you need the upgrade to support?” gives the agent something it can check. [Decisions question types](https://docs.parallel.ai/decisions/question-types)
