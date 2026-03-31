# PDF Processing API — Mainlayer

Pay-per-page PDF processing API. Extract text, tables, summaries, split or merge PDFs. Billing is handled by [Mainlayer](https://mainlayer.fr) on a per-page basis.

## Pricing

| Operation | Price |
|-----------|-------|
| Extract text | $0.005/page |
| Extract tables | $0.01/page |
| Summarize | $0.02/page |
| Split | $0.002/page |
| Merge | $0.01/call (flat) |

## Quick start

```bash
pip install -e ".[dev]"
MAINLAYER_API_KEY=sk_... uvicorn src.main:app --reload
```

## Example

```bash
# Extract text from a PDF
curl -X POST http://localhost:8000/pdf/extract-text \
  -H "X-Payer-Wallet: wallet_abc123" \
  -F "file=@document.pdf"
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/pricing` | Current price table (free) |
| `POST` | `/pdf/extract-text` | Extract text from all pages |
| `POST` | `/pdf/extract-tables` | Detect and extract tables |
| `POST` | `/pdf/summarize` | Extractive summary + key points |
| `POST` | `/pdf/split` | Split into single-page PDFs |
| `POST` | `/pdf/merge` | Merge multiple PDFs |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAINLAYER_API_KEY` | — | Your Mainlayer API key |
| `MAINLAYER_DEV_MODE` | `false` | Skip real billing (dev/test) |
| `MAX_FILE_SIZE_MB` | `50` | Max upload size in MB |

## Running tests

```bash
pytest tests/ -v
```
