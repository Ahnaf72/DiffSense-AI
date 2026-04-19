# DiffSense-AI - Sample API Calls

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication
All endpoints (except health) require authentication. Include JWT token in Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

## User Authentication

### Register User
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123",
    "full_name": "John Doe"
  }'
```

### Login
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepassword123"
  }'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

## Document Management

### Upload Document
```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "title=My Research Paper" \
  -F "file=@document.pdf"
```

Response:
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "title": "My Research Paper",
  "file_path": "uploads/document.pdf",
  "status": "processing",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Get Document
```bash
curl -X GET http://localhost:8000/api/v1/documents/{document_id} \
  -H "Authorization: Bearer <token>"
```

### List Documents
```bash
curl -X GET http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer <token>"
```

### Delete Document
```bash
curl -X DELETE http://localhost:8000/api/v1/documents/{document_id} \
  -H "Authorization: Bearer <token>"
```

## Document Analysis

### Analyze Document (Create Report)
```bash
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/analyze \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "report_id": "uuid",
  "status": "processing"
}
```

### Check Job Status
```bash
curl -X GET http://localhost:8000/api/v1/jobs/{job_id} \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "job_id": "uuid",
  "status": "completed",
  "progress": 100,
  "current_step": "storing_results",
  "result": {
    "status": "ok",
    "report_id": "uuid",
    "total_matches": 15,
    "aggregate_score": 0.75
  }
}
```

## Report Retrieval

### Get Basic Report
```bash
curl -X GET http://localhost:8000/api/v1/reports/{report_id} \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "id": "uuid",
  "user_id": "uuid",
  "document_id": "uuid",
  "overall_score": 0.75,
  "total_chunks": 42,
  "matched_chunks": 15,
  "status": "completed",
  "score_breakdown": {
    "final_score": 0.75,
    "breakdown": {
      "plagiarism": {"score": 0.8, "weight": 0.6, "match_count": 5},
      "paraphrase": {"score": 0.6, "weight": 0.3, "match_count": 8},
      "semantic": {"score": 0.4, "weight": 0.1, "match_count": 2}
    }
  },
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Get Detailed Report (Color-Coded)
```bash
curl -X GET http://localhost:8000/api/v1/reports/{report_id}/detailed \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "report_id": "uuid",
  "document_id": "uuid",
  "overall_score": 0.75,
  "total_matches": 15,
  "score_breakdown": { ... },
  "matches": [
    {
      "id": "uuid",
      "upload_chunk_id": "uuid",
      "upload_content": "The rapid advancement of artificial intelligence...",
      "upload_chunk_index": 5,
      "reference_chunk_id": "uuid",
      "reference_content": "Quick progress in AI technology...",
      "reference_chunk_index": 12,
      "reference_source_id": "ref_uuid",
      "reference_source_type": "reference",
      "similarity_score": 0.85,
      "color": "#ef4444",
      "severity": "high"
    }
  ],
  "segments": {
    "high": [...],
    "medium": [...],
    "low": [...]
  },
  "sources": ["ref_uuid1", "ref_uuid2"],
  "status": "completed",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Get Report Matches
```bash
curl -X GET http://localhost:8000/api/v1/reports/{report_id}/matches \
  -H "Authorization: Bearer <token>"
```

### List Reports
```bash
curl -X GET http://localhost:8000/api/v1/reports \
  -H "Authorization: Bearer <token>"
```

### Delete Report
```bash
curl -X DELETE http://localhost:8000/api/v1/reports/{report_id} \
  -H "Authorization: Bearer <token>"
```

## Admin Corpus Management (Admin Only)

### Upload Reference PDF
```bash
curl -X POST http://localhost:8000/api/v1/references/upload \
  -H "Authorization: Bearer <admin_token>" \
  -F "title=Reference Paper on AI" \
  -F "file=@reference.pdf"
```

Response:
```json
{
  "id": "uuid",
  "title": "Reference Paper on AI",
  "filename": "reference.pdf",
  "file_path": "uploads/ref_reference.pdf",
  "is_active": true,
  "uploaded_by": "admin_uuid",
  "created_at": "2024-01-01T00:00:00Z"
}
```

### Precompute Embeddings for Reference
```bash
curl -X POST http://localhost:8000/api/v1/references/{ref_id}/embed \
  -H "Authorization: Bearer <admin_token>"
```

Response:
```json
{
  "status": "ok",
  "ref_id": "uuid",
  "chunks_stored": 42,
  "embeddings_generated": 42
}
```

### List References
```bash
curl -X GET "http://localhost:8000/api/v1/references?active_only=true" \
  -H "Authorization: Bearer <token>"
```

### Toggle Reference Active Status
```bash
curl -X PATCH "http://localhost:8000/api/v1/references/{ref_id}/toggle?is_active=false" \
  -H "Authorization: Bearer <admin_token>"
```

### Delete Reference
```bash
curl -X DELETE http://localhost:8000/api/v1/references/{ref_id} \
  -H "Authorization: Bearer <admin_token>"
```

## Semantic Search

### Search Reference Chunks
```bash
curl -X POST http://localhost:8000/api/v1/documents/{document_id}/semantic-search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning algorithms",
    "threshold": 0.5,
    "top_k": 10
  }'
```

Response:
```json
{
  "query": "machine learning algorithms",
  "results": [
    {
      "chunk_id": "uuid",
      "chunk_index": 5,
      "content": "Machine learning algorithms are used for...",
      "similarity": 0.78
    }
  ]
}
```

## Health Check

### System Health
```bash
curl -X GET http://localhost:8000/api/v1/health
```

Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "services": {
    "database": "connected",
    "redis": "connected"
  }
}
```

## Complete Workflow Example

### 1. Register and Login
```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"pass123","full_name":"John"}'

# Login
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"pass123"}' \
  | jq -r '.access_token')
```

### 2. Upload Document
```bash
DOC_ID=$(curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "title=My Paper" \
  -F "file=@paper.pdf" \
  | jq -r '.id')
```

### 3. Analyze Document
```bash
REPORT_ID=$(curl -X POST http://localhost:8000/api/v1/documents/$DOC_ID/analyze \
  -H "Authorization: Bearer $TOKEN" \
  | jq -r '.report_id')
```

### 4. Get Detailed Report
```bash
curl -X GET http://localhost:8000/api/v1/reports/$REPORT_ID/detailed \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.'
```

## Error Responses

All errors follow this format:
```json
{
  "detail": "Error message here"
}
```

Common HTTP status codes:
- `400` - Bad Request (validation error)
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (admin-only endpoint, not admin)
- `404` - Not Found (resource doesn't exist)
- `500` - Internal Server Error (unexpected error)
