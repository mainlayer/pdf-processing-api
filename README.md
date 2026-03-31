# PDF Processing API

A production-ready PDF processing service with per-page billing via [Mainlayer](https://mainlayer.fr).

## Features

- **Text extraction**: Extract all text from PDFs with layout preservation
- **Table detection**: Automatically detect and extract structured tables
- **Summarization**: Generate extractive summaries with key points
- **Splitting**: Split multi-page PDFs into individual pages
- **Merging**: Combine multiple PDFs into a single document
- **Per-page billing**: Pay only for what you use
- **Flat-rate operations**: Merge is billed per-call, not per-page
- **Production-ready**: CORS, logging, error handling

## Pricing

| Operation | Cost | Use Case |
|-----------|------|----------|
| Extract text | $0.005/page | Get full text from PDFs |
| Extract tables | $0.01/page | Extract structured data |
| Summarize | $0.02/page | Generate summaries |
| Split | $0.002/page | Create single-page PDFs |
| Merge | $0.01/call | Combine PDFs (flat rate) |
| Pricing endpoint | FREE | View price table |

## 5-Minute Quickstart

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

### 2. Set environment variables

```bash
export MAINLAYER_API_KEY=your_api_key
export MAINLAYER_DEV_MODE=true  # Skip real billing during development
export MAX_FILE_SIZE_MB=50
export LOG_LEVEL=INFO
```

### 3. Start the server

```bash
uvicorn src.main:app --reload --port 8000
```

Server runs at `http://localhost:8000`

### 4. Check the pricing

```bash
curl http://localhost:8000/pricing
```

Response:
```json
{
  "operations": [
    {"name": "Extract Text", "operation": "extract_text", "price_usd": 0.005, "unit": "per page"},
    {"name": "Extract Tables", "operation": "extract_tables", "price_usd": 0.01, "unit": "per page"},
    {"name": "Summarize", "operation": "summarize", "price_usd": 0.02, "unit": "per page"},
    {"name": "Split", "operation": "split", "price_usd": 0.002, "unit": "per page"},
    {"name": "Merge", "operation": "merge", "price_usd": 0.01, "unit": "per call"}
  ]
}
```

### 5. Extract text from a PDF

```bash
curl -X POST http://localhost:8000/pdf/extract-text \
  -H "X-Payer-Wallet: wallet_demo_123" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "text": "Page 1 content...\n\nPage 2 content...",
  "page_count": 2,
  "amount_charged_usd": 0.01,
  "transaction_id": "txn_abc123"
}
```

### 6. Extract tables from a PDF

```bash
curl -X POST http://localhost:8000/pdf/extract-tables \
  -H "X-Payer-Wallet: wallet_demo_123" \
  -F "file=@spreadsheet.pdf"
```

## API Reference

### `GET /pricing`

List current pricing for all operations (FREE).

**Response**:
```json
{
  "operations": [
    {
      "name": "string",
      "operation": "extract_text | extract_tables | summarize | split | merge",
      "price_usd": 0.005,
      "unit": "per page | per call"
    }
  ]
}
```

---

### `POST /pdf/extract-text`

Extract all text from a PDF.

**Headers**:
- `X-Payer-Wallet`: Mainlayer wallet address to charge (required)

**Body** (multipart/form-data):
- `file`: PDF file to process (required, max 50 MB)

**Response**:
```json
{
  "text": "string",
  "page_count": 42,
  "amount_charged_usd": 0.21,
  "transaction_id": "txn_abc123"
}
```

**Cost**: $0.005 per page

---

### `POST /pdf/extract-tables`

Detect and extract tables from a PDF.

**Headers**:
- `X-Payer-Wallet`: Mainlayer wallet address (required)

**Body** (multipart/form-data):
- `file`: PDF file to process (required)

**Response**:
```json
{
  "tables": [
    {
      "page": 1,
      "table_index": 0,
      "data": [
        ["Column 1", "Column 2"],
        ["Row 1 Col 1", "Row 1 Col 2"]
      ]
    }
  ],
  "page_count": 42,
  "table_count": 5,
  "amount_charged_usd": 0.42,
  "transaction_id": "txn_abc123"
}
```

**Cost**: $0.01 per page

---

### `POST /pdf/summarize`

Generate an extractive summary of PDF content.

**Headers**:
- `X-Payer-Wallet`: Mainlayer wallet address (required)

**Body** (multipart/form-data):
- `file`: PDF file to summarize (required)

**Response**:
```json
{
  "summary": "This document discusses...",
  "key_points": [
    "First key point",
    "Second key point"
  ],
  "page_count": 42,
  "amount_charged_usd": 0.84,
  "transaction_id": "txn_abc123"
}
```

**Cost**: $0.02 per page

---

### `POST /pdf/split`

Split a multi-page PDF into individual single-page PDFs.

**Headers**:
- `X-Payer-Wallet`: Mainlayer wallet address (required)

**Body** (multipart/form-data):
- `file`: PDF file to split (required)

**Response**:
```json
{
  "pages": [
    {
      "page_number": 1,
      "pdf_base64": "JVBERi0xLjQK..."
    }
  ],
  "page_count": 42,
  "amount_charged_usd": 0.084,
  "transaction_id": "txn_abc123"
}
```

**Cost**: $0.002 per page

---

### `POST /pdf/merge`

Merge multiple PDF files into a single document.

**Headers**:
- `X-Payer-Wallet`: Mainlayer wallet address (required)

**Body** (multipart/form-data):
- `files`: Multiple PDF files to merge (required, 2–20 files)

**Response**:
```json
{
  "merged_pdf_base64": "JVBERi0xLjQK...",
  "input_file_count": 3,
  "output_page_count": 42,
  "amount_charged_usd": 0.01,
  "transaction_id": "txn_abc123"
}
```

**Cost**: $0.01 per merge (flat rate)

---

## Status Codes

| Code | Meaning | Trigger |
|------|---------|---------|
| 200 | Success | Operation completed |
| 400 | Bad Request | Missing header, empty file, invalid PDF |
| 402 | Payment Required | Wallet not found or insufficient balance |
| 413 | Payload Too Large | File exceeds 50 MB limit |
| 415 | Unsupported Media Type | File is not a valid PDF |
| 500 | Server Error | PDF processing failed |
| 503 | Service Unavailable | Mainlayer billing service unavailable |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAINLAYER_API_KEY` | (required) | Your Mainlayer API key |
| `MAINLAYER_BASE_URL` | `https://api.mainlayer.fr` | Mainlayer API endpoint |
| `MAINLAYER_DEV_MODE` | `false` | Skip real billing (for testing) |
| `MAX_FILE_SIZE_MB` | `50` | Max upload file size in MB |
| `MAX_MERGE_FILES` | `20` | Max files to merge in one call |
| `CORS_ORIGINS` | `*` | CORS allowed origins |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Examples

### Extract text from document

```bash
curl -X POST http://localhost:8000/pdf/extract-text \
  -H "X-Payer-Wallet: wallet_prod_123" \
  -F "file=@report.pdf" \
  | jq '.text' | head -50
```

### Extract all tables

```bash
curl -X POST http://localhost:8000/pdf/extract-tables \
  -H "X-Payer-Wallet: wallet_prod_123" \
  -F "file=@financial_statements.pdf" \
  | jq '.tables[0].data'
```

### Merge multiple PDFs

```bash
curl -X POST http://localhost:8000/pdf/merge \
  -H "X-Payer-Wallet: wallet_prod_123" \
  -F "files=@chapter1.pdf" \
  -F "files=@chapter2.pdf" \
  -F "files=@chapter3.pdf" \
  | jq -r '.merged_pdf_base64' | base64 -d > book.pdf
```

### Split and summarize

```bash
# 1. Split into pages
curl -X POST http://localhost:8000/pdf/split \
  -H "X-Payer-Wallet: wallet_prod_123" \
  -F "file=@document.pdf" \
  > pages.json

# 2. Summarize for overview
curl -X POST http://localhost:8000/pdf/summarize \
  -H "X-Payer-Wallet: wallet_prod_123" \
  -F "file=@document.pdf" \
  | jq '.key_points'
```

---

## Production Deployment

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pdf-processing-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pdf-processing-api
  template:
    metadata:
      labels:
        app: pdf-processing-api
    spec:
      containers:
      - name: api
        image: pdf-processing-api:latest
        ports:
        - containerPort: 8000
        resources:
          limits:
            cpu: "1"
            memory: "512Mi"
          requests:
            cpu: "500m"
            memory: "256Mi"
        env:
        - name: MAINLAYER_API_KEY
          valueFrom:
            secretKeyRef:
              name: mainlayer
              key: api-key
```

---

## Development

### Running tests

```bash
pytest tests/ -v
```

### Linting

```bash
black src/ tests/
mypy src/
```

---

## Production Checklist

- [ ] Configure HTTPS/TLS
- [ ] Set up CORS properly (restrict origins)
- [ ] Enable request logging and monitoring
- [ ] Configure rate limiting per wallet
- [ ] Set up Prometheus metrics
- [ ] Enable distributed tracing
- [ ] Test billing integration with live Mainlayer account
- [ ] Configure auto-scaling
- [ ] Set up backup/disaster recovery
- [ ] Document SLA and uptime targets

---

## Support

- Docs: https://docs.mainlayer.fr
- Issues: https://github.com/mainlayer/pdf-processing-api/issues
