# Deployment Guide - Railway

This guide covers deploying the Aurora Q&A API service to Railway without exposing your IP address.

## Prerequisites

- GitHub account
- Railway account (free at [railway.app](https://railway.app))
- Environment variables:
  - `OPENAI_API_KEY` - Your OpenAI API key
  - `MEM0_API_KEY` - Your mem0 API key
  - `MESSAGES_API_BASE` - (Optional) Defaults to the November 7 API

## Deployment Steps

1. **Sign up** at [railway.app](https://railway.app) (free tier available)

2. **Create a new project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"

3. **Connect your GitHub repository**:
   - Authorize Railway to access your GitHub
   - Select repository: `LittleMonsterSen/Aurora-Q-A`
   - Railway will automatically detect the Dockerfile

4. **Add environment variables**:
   - Go to your project → Variables tab
   - Add the following:
     - `OPENAI_API_KEY` = your OpenAI API key
     - `MEM0_API_KEY` = your mem0 API key
     - `MESSAGES_API_BASE` = (optional) defaults to November 7 API

5. **Deploy**:
   - Railway will automatically start building and deploying
   - Watch the build logs in real-time
   - Once deployed, your service will be available at: `https://your-app-name.up.railway.app`

6. **Get your public URL**:
   - Go to Settings → Generate Domain
   - Or use the auto-generated domain

## Testing Your Deployment

Once deployed, test your API:

```bash
# Health check
curl https://your-app-name.up.railway.app/healthz

# Ask a question (GET)
curl "https://your-app-name.up.railway.app/ask?question=What%20is%20Sophia's%20diet%20preference"

# Ask a question (POST)
curl -X POST https://your-app-name.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Sophia'\''s diet preference"}'
```

## API Endpoints

- `GET /healthz` - Health check endpoint
- `GET /ask?question=...` - Ask a question (query parameter)
- `POST /ask` - Ask a question (JSON body: `{"question": "..."}`)

## Response Format

```json
{
  "answer": "Sophia Al-Farsi is vegetarian and prefers gluten-free options..."
}
```

## Advantages of Railway

- ✅ **Free tier available** - No credit card required for basic usage
- ✅ **Automatic HTTPS** - SSL certificates included
- ✅ **GitHub integration** - Auto-deploy on push
- ✅ **Simple environment variable management**
- ✅ **Real-time logs** - Easy debugging
- ✅ **No IP exposure** - Your IP address stays private

## Troubleshooting

- **Build fails**: Check that all dependencies are in `requirements.txt`
- **Service crashes**: Check logs in Railway dashboard
- **Environment variables not working**: Ensure they're set in Railway Variables tab, not in `.env` file
- **Names index not found**: Ensure `data/index/names.json` exists and is committed to Git

## Local Testing

Before deploying, test locally with Docker:

```bash
# Build the image
docker build -t aurora-qa .

# Run with environment variables
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your_key \
  -e MEM0_API_KEY=your_key \
  aurora-qa

# Test
curl "http://localhost:8000/ask?question=What%20is%20Sophia's%20diet%20preference"
```
