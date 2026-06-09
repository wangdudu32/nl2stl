# API validation interface

`llm_validate.py` validates one STL/NL candidate with one independent Responses API request. It does not generate candidates or update dataset progress.

## Configuration

- API key: `OPENAI_API_KEY`
- Default model: `OPENAI_MODEL`
- Optional API base URL: `OPENAI_BASE_URL` (default: `https://api.openai.com/v1`)

The API key is never written to output files.

## Usage

```bash
export OPENAI_API_KEY='your-api-key'
export OPENAI_MODEL='your-model-id'

python src/llm_validate.py \
  --input src/validation_request.example.json \
  --output /tmp/validation_result.json
```

Override the model for one call:

```bash
python src/llm_validate.py \
  --model 'your-model-id' \
  --input src/validation_request.example.json
```

Check the input and outgoing payload without an API key or network request:

```bash
python src/llm_validate.py \
  --model 'your-model-id' \
  --input src/validation_request.example.json \
  --dry-run
```

Exit codes:

- `0`: validation passed
- `2`: validation completed but failed
- `1`: input, configuration, API, or response error

The output JSON contains `verdict`, `issues`, `suggestions`, and non-secret validator metadata. A resumed generator should use the feedback to revise the candidate, call this script again with a fresh request, and only write the final dataset record after a `PASS` result.
