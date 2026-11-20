# Local RAG evaluation harness

The evaluation harness runs deterministic allowed, denied, answer, source, and
citation checks without API keys or network services. It uses fictional fixture
documents and an evaluation-only keyword retriever and answer provider.

Run it from the repository root:

```bash
python3.12 -m reference_service.evaluation \
  --json-report .local/evaluation-report.json
```

The command prints a short result for each case and exits non-zero when a case
fails. The JSON report records the case ID, persona, returned source and citation
IDs, and each failure reason. It deliberately omits full questions and answers
from the report so that the output format remains suitable for future fixtures
that may be more sensitive.

## Case format

`evaluation/cases.json` is versioned and contains:

- `id`: stable case identifier;
- `question`: synthetic input used by the fake retriever;
- `persona_id`: fake persona under evaluation;
- `allowed_roles`: roles permitted to use the evidence, for reviewer context;
- `allowed_source_ids`: maximum source and citation allow-list;
- `expected_source_ids`: exact sources expected from this target;
- `expected_answer.refused`: whether the target must refuse;
- `expected_answer.required_terms`: minimal deterministic answer properties.

To add a regression, add one small synthetic case, run the command above, and
add a focused unit test when the new case covers a new failure rule. Never use
real prompts, document text, credentials, personal data, or customer identifiers.

## What is checked

The evaluator fails a case when the target:

- returns or cites an ID outside the case allow-list;
- returns malformed source metadata or a citation without a matching source;
- omits or adds an expected source;
- returns an allowed answer without its expected citation;
- refuses an allowed case or answers a case that must be refused;
- attaches evidence to a refusal;
- omits a required answer term.

## Trust boundary and limitations

This harness evaluates a deterministic fake target. The fake target performs a
small audience filter so denied-case regressions can be exercised, but it is not
connected to `ReferenceService`, the static UI, an identity provider, a model,
or a production retrieval system. Passing these cases proves the evaluator can
detect the included regressions; it does not prove that NexusVault currently
enforces authorization. The public demo must remain labeled as simulated until
the policy and retrieval roadmap work is connected and reviewed.
