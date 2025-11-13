# API Usage Guide

## Getting Your API Endpoint

After deploying to Railway:

1. Go to your Railway project dashboard
2. Click on your service
3. Go to **Settings** → **Domains**
4. You'll see your public URL: `https://your-app-name.up.railway.app`
5. Or click **Generate Domain** to create a custom domain

## API Endpoints

### Base URL
```
https://your-app-name.up.railway.app
```

### 1. Health Check
Check if the API is running:

```bash
GET /healthz
```

**Example:**
```bash
curl https://your-app-name.up.railway.app/healthz
```

**Response:**
```json
{
  "ok": true
}
```

### 2. Ask a Question (GET)
Ask a question using query parameter:

```bash
GET /ask?question=YOUR_QUESTION
```

**Example:**
```bash
curl "https://your-app-name.up.railway.app/ask?question=What%20is%20Sophia's%20diet%20preference"
```

**Response:**
```json
{
  "answer": "Sophia Al-Farsi is vegetarian and prefers gluten-free options..."
}
```

### 3. Ask a Question (POST)
Ask a question using JSON body:

```bash
POST /ask
Content-Type: application/json

{
  "question": "YOUR_QUESTION"
}
```

**Example with curl:**
```bash
curl -X POST https://your-app-name.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Sophia'\''s diet preference"}'
```

**Example with PowerShell:**
```powershell
$body = @{ question = "What is Sophia's diet preference" } | ConvertTo-Json -Compress
$response = Invoke-RestMethod -Uri 'https://your-app-name.up.railway.app/ask' -Method Post -ContentType 'application/json' -Body $body
$response.answer
```

**Example with JavaScript (fetch):**
```javascript
const response = await fetch('https://your-app-name.up.railway.app/ask', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    question: "What is Sophia's diet preference"
  })
});

const data = await response.json();
console.log(data.answer);
```

**Example with Python (requests):**
```python
import requests

url = "https://your-app-name.up.railway.app/ask"
payload = {"question": "What is Sophia's diet preference"}
response = requests.post(url, json=payload)
print(response.json()["answer"])
```

## Response Format

All endpoints return JSON:

```json
{
  "answer": "The answer to your question..."
}
```

## Error Responses

### 400 Bad Request
```json
{
  "detail": "question must be at least 3 characters"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to answer the question: [error details]"
}
```

## Testing Your Deployment

1. **Test health check:**
   ```bash
   curl https://your-app-name.up.railway.app/healthz
   ```

2. **Test with a question:**
   ```bash
   curl "https://your-app-name.up.railway.app/ask?question=When%20does%20Sophia%20plan%20to%20have%20private%20dinner"
   ```

3. **View logs in Railway:**
   - Go to your service → **Deployments** → Click on latest deployment
   - View real-time logs to debug any issues

## Environment Variables Required

Make sure these are set in Railway:
- `OPENAI_API_KEY` - Your OpenAI API key
- `MEM0_API_KEY` - Your mem0 API key
- `MESSAGES_API_BASE` - (Optional) Defaults to November 7 API

## CORS

The API has CORS enabled by default, allowing requests from any origin. You can restrict this by setting the `CORS_ALLOW_ORIGINS` environment variable in Railway.

